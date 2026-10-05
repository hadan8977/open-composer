# T-58 配置第二版的来源存档（2026-10-05）

19:07 主审轮（Opus）在写 `reports/research/iterations/t20261005_p4_alloc_v2/` 之前下载。HTML 页面用 python 去标签转成同名 `.txt`；PDF 在 `pdf/`（不提交），文本由 `pdftotext -layout` 转换。卡片和哈希在 `reports/harness/source_cards/t20261005_p4_alloc_v2.jsonl`。

| 文件 | 来源 | 关键内容 | 口径和边界 |
|---|---|---|---|
| `mrt2010_erc.txt` | thierry-roncalli.com/download/erc.pdf（JPM 36(4) 2010） | ERC 组合的波动介于最小方差和 1/N 之间 | 理论和指数示例，没有讲 sleeve 组合或夏普增量 |
| `dgu2009_repec.txt` | ideas.repec.org（RFS 22(5) 2009，只有摘要） | 14 个优化模型没有一个稳定胜过 1/N；25 个资产要约 3000 个月的估计窗 | 全文付费，LBS 仓库没有全文 |
| `palomar_ch11_risk_parity.txt` | bookdown.org/palomar（Cambridge 2025 教科书第 11 章） | 风险平价分配风险而不是资金；凸形式求解 | 教科书综述 |
| `alpaca_margin.txt` | docs.alpaca.markets margin-and-short-selling（2026-10-05 抓取） | 初始 50%；隔夜维持：>6 美元 30%、2 倍 ETF 50%、3 倍 ETF 75%；借款 6.50%/360；单一持仓超 70% 且借款 ≥10 万时维持 50% | 以抓取日为准，实盘账户可能不同 |
| `finra_rn09-53.txt` | finra.org Regulatory Notice 09-53 | 杠杆 ETF 的维持保证金按杠杆倍数提高（多头 25% × 倍数，上限 100%） | 行业最低线 |

检索词：见 `direction-review.json` 的 `queries`。复用的旧存档：DSR、Magdon-Ismail、Kaminski–Lo（`evaluation-standard-2026-10-01/`），Roncalli–Weisang（`p2-s1-theme-budget-2026-10-05/`）。

版权说明：PDF 只作个人研究存档，不外发。
