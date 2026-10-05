import json
R = json.load(open("results.json"))
CAPS = [str(c) for c in R["capitals"]]
fmt = lambda c: f"{int(c)//1000}k" if int(c) < 1_000_000 else f"{int(c)/1e6:g}M"
pc = lambda x: f"{x*100:.1f}%"

def etf_cell(k, C):
    c = R["etf_sleeves"][k]["by_capital"][C]; f = c["whole_share_floor"]
    return f"{'过' if c['v2_whole_share_pass'] else '否'}；整股敞口比 {f['exposure_ratio']:.3f}，零股名 {f['zero_names']}/{f['n_names']}，L1 {pc(f['rel_l1_error'])}"

def stock_cell(form, C):
    m = R["stock_books"][form]["by_capital"][C]["mixed"]
    v = m["v2"]; fails = [n for n, key in (("空头敞口", "short_ratio_ok"), ("L1", "rel_l1_ok"), ("净美元", "net_dollar_ok"), ("ADV", "adv_1pct_ok")) if not v[key]]
    return (f"{'过' if v['pass'] else '否（' + '、'.join(fails) + '）'}；空头零股 {pc(m['short_zero_frac'])}，空头敞口比 {m['short_gross_ratio']:.2f}，"
            f"多头零股 {pc(m['long_zero_frac'])}（碎股下多头敞口比 {m['long_gross_ratio']:.2f}），L1 {pc(m['rel_l1_error'])}，净美元偏离 {m['net_dollar_err_pct_equity']*100:+.1f}%")

head = "| 资金 | S1 | S2 | S3 | C2 | v1.2 F1 | v1.2 F2 | P1 腿（F1 股票腿代理） |\n|---|---|---|---|---|---|---|---|\n"
rows = ""
for C in CAPS:
    rows += f"| ${fmt(C)} | " + " | ".join([etf_cell(k, C) for k in ("S1", "S2", "S3", "C2")] + [stock_cell("F1", C), stock_cell("F2", C), stock_cell("F1", C)]) + " |\n"
main_table = head + rows

eng = "| 资金 | F1 引擎现状（整股两边，最小 $100）空头敞口比 / 多头敞口比 / L1 | F2 同 |\n|---|---|---|\n"
for C in CAPS:
    a = R["stock_books"]["F1"]["by_capital"][C]["engine"]; b = R["stock_books"]["F2"]["by_capital"][C]["engine"]
    eng += f"| ${fmt(C)} | {max(a['short_gross_ratio'],0):.2f} / {a['long_gross_ratio']:.2f} / {pc(a['rel_l1_error'])} | {max(b['short_gross_ratio'],0):.2f} / {b['long_gross_ratio']:.2f} / {pc(b['rel_l1_error'])} |\n"

rt = "| 资金 | " + " | ".join(f"前{n}/边" for n in (50, 100, 200, 300, 500)) + " |\n|---|---|---|---|---|---|\n"
for C in CAPS:
    cells = []
    for n in (50, 100, 200, 300, 500):
        x = R["small_n_feasibility"][f"top{n}_per_side"][C]
        cells.append(f"{'过' if x['v2_pass'] else '否'}（空头零股 {pc(x['short_zero_frac'])}，敞口比 {x['short_gross_ratio']:.2f}）")
    rt += f"| ${fmt(C)} | " + " | ".join(cells) + " |\n"

pv = "| 总资金 | S3 子仓 | C2 子仓 | F2 子仓 | F1 子仓 |\n|---|---|---|---|---|\n"
for C in CAPS:
    p = R["program_view"][C]
    pv += (f"| ${fmt(C)} | ${p['S3']['sleeve_capital']:,.0f}：{'过' if p['S3']['etf_whole_share_pass'] else '否'} | ${p['C2']['sleeve_capital']:,.0f}：{'过' if p['C2']['etf_whole_share_pass'] else '否'} | "
           f"${p['F2']['sleeve_capital']:,.0f}：{'过' if p['F2']['v2_pass'] else '否'}（空头零股 {pc(p['F2']['short_zero_frac'])}） | ${p['F1']['sleeve_capital']:,.0f}：{'过' if p['F1']['v2_pass'] else '否'}（空头零股 {pc(p['F1']['short_zero_frac'])}） |\n")

mg = "| 资金 | F1 Reg T 初始保证金 ÷ 净值 | F2 |\n|---|---|---|\n"
for C in CAPS:
    mg += f"| ${fmt(C)} | {R['margin']['F1'][C]['reg_t_initial_over_equity']:.2f} | {R['margin']['F2'][C]['reg_t_initial_over_equity']:.2f} |\n"

rb = R["raw_backtest"]; dr = R["deflated_return_range"]; di = R["dsr_inputs"]
ret = "| 子策略 | 全期年化 | 锚定窗（2024-01..2026-09）年化 | 锚定窗波动 | DSR 折后预期（超额现金，年化） | 状态 |\n|---|---|---|---|---|---|\n"
for k in ("S1", "S2"):
    ret += f"| {k} | {pc(rb[k]['full']['cagr'])} | {pc(rb[k]['anchor']['cagr'])} | {pc(rb[k]['anchor']['vol'])} | 待定 | 本任务自算（returns.parquet net10，未扣无风险利率）；试验数未知；**未折扣** |\n"
for k in ("S3", "C2"):
    ret += f"| {k} | {pc(rb[k]['full']['cagr'])} | {pc(rb[k]['anchor']['cagr'])} | {pc(rb[k]['anchor']['vol'])} | 待定 | allocation-dd30 engine_stats；试验数未知；**未折扣** |\n"
for k in ("F1", "F2"):
    ret += f"| {k} | {pc(rb[k]['full']['cagr'])} | {pc(rb[k]['anchor']['cagr'])} | {pc(rb[k]['anchor']['vol'])} | {pc(dr[k]['deflated_excess_return_low'])} – {pc(dr[k]['deflated_excess_return_high'])}（原始锚定超额 {pc(dr[k]['raw_anchor_excess_return'])}） | 折扣用 v1.2 M0_U3000 的 DSR 输入，见下 |\n"
ret += f"| P1 腿 | — | — | — | 待定（无记分卡；F1 数字仅作代理参考） | P1 尚无自己的回测与试验登记 |\n"

report = f"""# T-20261004-71 / R1005-T71：资金档位与整股可实现性（写给机主）

生成：{R['generated_at_utc']}（UTC）。脚本 `compute.py` / `build_report.py`，全部数字来自同目录 `results.json`。只读研究数据与目标文件，没有下单、没有调用任何券商交易接口。

## 结论（先看这里）

1. **ETF 四条（S1、S2、S3、C2）在 1 万美元起就能原样上。** 目标只有 2–3 只 ETF，整股取整后敞口比 ≥0.94（1 万档最差是 C2 0.942），没有零股名字；多头还可以用碎股（见下，但碎股只能下 day 单，不能参加开盘/收盘竞价）。
2. **v1.2（F1、F2）原样上要 25 万美元以上。** 空头必须整股，1 万档 F1 有 89.7% 的空头名字取整为 0 股（敞口比 0.29），10 万档仍有 40.5%（0.89）。按我对标准 v2.1 V2 的量化（空头敞口比 ≥0.90、相对 L1 ≤30%、净美元偏离 ≤5%、持仓 ≤ 20 日成交额 1%），**只有 25 万档的 F1、F2 过**；10 万档 F1 差一点（敞口比 0.89，净偏离 5.2%），F2 不过。
3. **按 10-02 的组合权重（S3 0.60、C2 0.335、F2 0.12、F1 0.025），F1、F2 的子仓在 25 万以下的总资金里都不够大**（F2 子仓 25 万档只有 $30,000，空头零股 82%）。所以 v1.2 在小资金下的唯一出路是**集中版**（每边 N 只）：只看取整可行性，前 100/边 在 2.5 万起可行，前 200/边 在 5 万起，前 300/边 在 10 万起。**集中版会损失多少夏普还没测**，是 10-08 至 10-14 小资金构造任务的内容；这里不下结论。
4. **推荐：起步档 5 万美元，只上 ETF 子策略（S3 为主，C2 为辅，按 10-02 权重）；v1.2 先不上。** 2.5 万美元是下限（ETF 仍可行，但 C2 子仓只有 $8k，SPY 一股 $763，取整误差 6% 量级）。v1.2 实盘要么总资金到 25 万以上，要么等集中版测试通过再在 5–10 万档上。1 万美元不推荐：ETF 能上，但 S3 全期最大回撤 −48%（锚定窗 −32%），按 0.60 权重就是账户的 −29%，而 F 腿完全上不了，等于只做 ETF 且分散很弱；单笔 $1k 级的整股误差和费用占比也更高。
5. **规则核对的两处更正**：①我们执行配置里的"最小下单额 $100"是**我们自己定的**（`open_composer/book_paper/plan.py` 的 `min_notional=100.0` 默认值，CLI 同值），不是 Alpaca 的限制；Alpaca 对买入单的最小名义额是 $1。引擎现状（整股两边加 $100 下限）在 25 万档仍丢掉 56% 的多头名字（见下表），所以小资金要先改引擎，不改的话数字比上表更差。②PDT 对我们基本无影响：FINRA 新规 2026-06-04 生效，Alpaca 已取消 $25,000 门槛；v1.2 和 ETF 都是隔夜持有，本来就不触发。

## 一、规则核对（官方原文）

抓取时间均为 2026-10-05 约 05:53–05:58 UTC。注意：网页由工具内置的小模型摘要后返回，下面引号内文字是摘要中标明为原文的句子，**未逐字对照原页面**；关键数字（$1、$2,000、2026-06-04、2027-10-20）有两个以上来源一致。

| 事项 | 原文要点 | 来源 |
|---|---|---|
| 碎股标的 | "Not all assets are fractionable yet so please make sure you query assets details to check for the parameter `fractionable = true`." | https://docs.alpaca.markets/docs/fractional-trading |
| 碎股做空 | "We do not support short sales in fractional orders." | 同上 |
| 碎股订单类型和时效 | 市价、限价、止损、止损限价，**time in force = Day**（订单文档同：碎股不支持 GTC，也就不在 opg/cls 竞价单之列） | 同上；https://docs.alpaca.markets/docs/orders-at-alpaca |
| 碎股最小名义额 | 文档页没写具体数；支持页："we enforce a minimum 1 USD notional amount for Buy entry orders." 该页没区分实盘和模拟盘 | https://alpaca.markets/support/can-we-submit-orders-smaller-than-1-usd-in-notional-value |
| 碎股日内交易 | "Day trading fractional shares counts towards your day trade count."（页面仍是旧文字，与 Alpaca 博客的新规说明不一致，待 Alpaca 更新；对我们无影响，因为不做日内） | 碎股文档 |
| 做空门槛 | "In order to trade on margin or sell short, you must have $2,000 or more account equity." 易借券（ETB）"$0 locate and borrow fees on all ETB shares for Trading API users"；难借券需批准的 locate，"round lots of 100 shares" | https://docs.alpaca.markets/docs/margin-and-short-selling |
| 空头维持保证金 | 价格 <$5：每股 $2.50 与 100% 取大；≥$5：每股 $5.00 与 30% 取大 | 同上 |
| PDT 新规 | FINRA Regulatory Notice 26-10，2026-04-20 发布；生效 2026-06-04；会员可分阶段实施，**最迟 2027-10-20**；取消日内交易次数认定和 $25,000 最低净值，改为按日内保证金亏空监控 | https://www.finra.org/rules-guidance/notices/26-10 |
| Alpaca 实施 | 2026-04-27 发文、06-04 更新：$25,000 门槛已去掉，4 倍日内购买力的最低净值降到 $2,000；API 里的日内交易字段 2026-07-06 全部移除；曾被 PDT 限制的账户已解除 | https://alpaca.markets/blog/finra-retires-the-pdt-rule-introducing-alpacas-new-intraday-margin-framework/ |
| SEC 批准（第三方） | 2026-04-14 批准；与上面的 FINRA 原文一致 | https://www.acaglobal.com/industry-insights/finra-ends-the-pattern-day-trader-rule/ （未读原页，仅搜索摘要） |

这修正了情报 I-05 第 139 行和计划里"Alpaca 没写实施日期"的说法：Alpaca 自己的页面写了（2026-06-04 起，API 字段 07-06 移除）。实盘账户是否已迁移到新框架、我们的账户是否具备保证金账户资格，**仍未核对**（要看机主的实盘账户页面）。

**对执行的含义**：多头碎股可以降低 v1.2 多头腿的取整误差，但碎股只能下 day 单，**不能用开盘、收盘竞价**。v1.2 的设计是开盘/收盘价成交（计划 5b 的"开盘前置"）。所以小资金下多头走碎股 = 放弃竞价成交，改成盘中限价或市价，成交价口径要重做（计划里的成本表是按竞价和 NBBO 半价差测的）。这一点会影响 F 腿净收益，没有量化。

## 二、资金和可实现性表（每个子策略单独按资金 C 计）

口径：
- 目标文件：S1–S3、C2 用 `reports/execution/*-target-weights.json`（信号日 10-02 或 09-30，生成 10-02 夜）；F1、F2 用 `reports/paper/book/quant1|quant2/targets/2026-10-02.json`（1784 个名字）。P1 腿用 F1 的股票多空两腿做**代理**（P1 本身尚无目标文件）。
- ETF：长仓整股向下取整（不超现金）；碎股可用时误差更小。
- F1/F2：多头碎股（≥$1），空头整股（四舍五入，0.5 远离零）；核心 SGOV/SPY 与对冲 SPY 视为碎股可精确持有。"空头零股"是目标空头名字里取整后为 0 股的比例；与计划第 5 节表在空头零股和敞口比两列逐位一致（复算）。
- V2 的量化是我定的（标准 v2.1 的 V2 没给数）：空头敞口比 ≥0.90；相对 L1 误差（Σ|实现−目标| ÷ Σ|目标|）≤30%；净美元偏离 ≤净值 5%（引擎 `RiskLimits.max_abs_net` 的现有值）；最大持仓 ≤20 日成交额 1%（标准原文）。阈值在看结果前定下。成交量一条所有格都过（最大持仓占 20 日成交额不到 0.02%）。

{main_table}
**读表要点**：F1/F2 在小资金下"净美元偏离"为正，是因为空头被取整丢掉而多头（碎股）还在，账户变成净多头；10 万档 F1 净偏离 +5.2%，已超引擎的 5% 限额。可以把多头按实现的空头同比例缩小来保持净中性，但会同比例丢掉阿尔法，这是构造任务要比较的方案之一。

**引擎现状更差**（整股两边加 $100 最小下单额，未改引擎时的结果）：

{eng}

**保证金占用**（Reg T 初始 50%，实现的多空市值）：

{mg}
全部不超过 1.0，但 F1 在 25 万档已达 0.90，空头维持保证金和单一持仓集中规则（Alpaca 文档：集中时升到 50%）的余量不大，没单独建模。

## 三、按 10-02 组合权重分配后的子仓可实现性

10-02 权重（S3 0.60、C2 0.335、F2 0.12、F1 0.025，另借 8%）是研究者定的纸面分配，可能随 T-75/T-58 改变。子仓资金 = 权重 × 总资金，ETF 按整股向下取整，判"过"= 敞口比 ≥0.90 且无零股：

{pv}
## 四、按 DSR 打折后的预期年化收益区间

输入与方法：
- 有 DSR 输入的只有 v1.2：`reports/research/iterations/t20261002_book_v12/results.json` 的 M0_U3000：近期净夏普 {di['recent_net_sharpe']:.3f}（{di['recent_sessions']} 个会话）；家族 SR0 {di['family_sr0_annual']:.3f}（家族 DSR {di['family_dsr']:.3f}）；组合级 SR0 {di['program_sr0_annual']:.3f}（组合级 DSR {di['program_dsr']:.3f}）。
- 折扣系数 = (SR − SR0) ÷ SR：家族口径 {di['haircut_factor_family']:.3f}（高端），组合口径 {di['haircut_factor_program']:.3f}（低端）。预期超额收益 ≈ 折扣系数 × 锚定窗夏普 × 锚定窗波动，数字来自 allocation-dd30 的 engine_stats。
- **假设**：把 M0_U3000 的折扣系数用到 F1、F2 两种形式上（它们是同一个账本的两种构造，没有各自的 SR0）；F2 含 SPY 核心仓，对总夏普一起打折，对 beta 部分偏保守。
- 区间不含：取整损失（V2 不过的格不适用）、碎股放弃竞价的成本变化、真实滑点、借券（ETB 零费）。

{ret}
ETF 四条没有 DSR 输入（没有记分卡，试验数没登记），所以**不给折后数**，只给原始回测，**没打折**。S3 锚定年化 118.8% 来自看过 2023–2025 的补救设计（allocation-dd30 报告第 1 条警告），不能当预期。

## 五、别人怎样做小资金多空（给小资金构造任务）

1. **基数约束 + 整手的混合整数优化。** Murray & Shek（Computational Optimization and Applications，2012，DOI 10.1007/s10589-012-9471-1）：基数约束均值方差问题 NP-hard，用"局部松弛"——先把资产收益投影到低维再聚类，在小的局部二次规划里选名字；3,000 只股票规模下比分支切割法快，作者点名用途是指数跟踪、高频套利。（已读摘要和引言。）用法：从 1784 个名字里选 K 个，K 由资金和价格定。
2. **整手约束的精确法。** 搜索结果显示有"带整手约束的因子模型组合选择精确算法"和"基数约束均值方差的最优手数解"两类文献，用分支定界加拉格朗日松弛。**只见到标题摘要，没读正文**，列为待读，不当成已核实。
3. **每边要多少只。** Statman 1987（JFQA 22(3)，353–363）：随机选股要 30 只（借钱投资者）到 40 只（放贷）才算分散；Campbell, Lettau, Malkiel, Xu 2001（Journal of Finance，NBER w7590）：1962–1997 个股特质波动上升，达到同等分散所需只数增加，50 只组合的标准差只小幅上升。含义：每边 50 只以上特质风险已大体分散，但我们的名字是按信号挑的，不是随机抽的，所以集中损失的是信号覆盖，不只是分散度。（只读了摘要。）
4. **约束对信息转化的损失。** Clarke, de Silva, Thorley 2002（Financial Analysts Journal 58(5)，48–66）的转移系数：约束（禁空、集中度）使信号只能部分转为组合权重。用法：小资金构造任务把"集中版相对完整版的转移系数 / 同波动夏普"作为预注册指标，而不是只报收益。（只读了摘要。）
5. **先取整再用液态 ETF 对冲残差**（本任务自己的推导，非文献）：空头整股取整后，用 SPY 重新按实现的 beta 对冲，净美元偏离用多头碎股缩放。beta 对冲在 SPY 上无取整问题；本表的"净美元偏离"和 results.json 里的 `net_beta_err_pct_equity` 就是需要被对冲的量。

只看取整可行性的集中版筛选（**不含收益影响，尚未测**；按 F1 股票腿，每边取权重绝对值最大的 N 只，各边总额按原值缩放回去）：

{rt}
## 六、推荐

| 总资金 | 能原样上 | 要改构造 | 说明 |
|---|---|---|---|
| 1 万 | S1、S2、S3、C2（C2 子仓只有 $3.4k，敞口比 0.90 贴着线，建议用碎股） | F1、F2、P1 腿 | 不推荐：S3 回撤按 0.60 权重占账户约 29%，F 腿上不了，分散弱 |
| 2.5 万 | 四条 ETF | F 腿；集中版前 100/边勉强可行 | 下限档 |
| **5 万（推荐起步）** | 四条 ETF，按 10-02 权重 | F 腿用前 ≤200/边的集中版，**待 10-14 的构造测试** | ETF 误差 ≤1.3%；v1.2 暂不上 |
| 10 万 | 四条 ETF | F1 临界（敞口比 0.89，净偏离 5.2%），F2 不过；集中版前 ≤300/边可行 | 可以在构造任务通过后加 v1.2 小仓 |
| 25 万 | 四条 ETF；F1、F2 单独算过 V2 | F 腿在组合权重下的子仓（F2 $30k、F1 $6k）仍不够，要么提权重要么用集中版 | 要原样上 v1.2，总资金至少 25 万且 F 子仓各自接近 25 万——按现权重 F2 子仓到 25 万要总资金约 210 万 |

**理由**：这个资金区间里，约束来自"空头只能整股"，不是收益。ETF 子策略的约束只是整股取整，几乎无损；v1.2 的阿尔法在空头腿，空头腿在 10 万以下被取整打掉一半以上。所以先让 ETF 上去，v1.2 靠集中版构造的测试结果再决定，不靠加资金硬上。计划里的分档（L1 试点规模是目标规模的 10–20%）也要对着这张表看：如果目标规模是 50 万，试点 5–10 万只能装下 ETF。

## 七、没有做的，和拿不准的

- **集中版的收益影响没测**（属于 10-08 至 10-14 的构造任务）；这里只测了取整可行性。
- **V2 的量化阈值是我定的**，标准 v2.1 没给数。边缘格（10 万档 F1：敞口比 0.89 对 0.90、净偏离 5.2% 对 5%）按阈值判否，但差得很小。
- DSR 折扣把 M0_U3000 的 SR0 套用到 F1/F2 上；ETF 四条无折后数。
- 引擎现状的 $100 下限和整股多头是代码事实，但 v1.2 的真实订单是按 10-05 18:30 彩排的 plan 生成，本表用的是 10-02 目标文件，与彩排结果可能略有差。
- 未核对：机主实盘账户是否已迁移到新日内保证金框架、是否具备保证金账户资格；Alpaca 碎股、订单文档页面上"最小名义额"只在支持页出现，未见写在 API 文档里；碎股"day 单、不能竞价"来自文档摘要。
- 用到的网页由内置小模型摘要返回，非原页逐字核对。
"""
open("report.md", "w").write(report)
# append sources/recommendation to results.json
R["rules_checked_at_utc"] = "2026-10-05T05:53Z..05:58Z"
R["rules"] = {
 "fractional_short": "not supported (docs.alpaca.markets/docs/fractional-trading)",
 "fractional_tif": "Day only; no GTC, so no opg/cls auctions",
 "fractional_min_notional": "$1 for buy entry orders (alpaca.markets/support/can-we-submit-orders-smaller-than-1-usd-in-notional-value)",
 "engine_min_notional_100": "our own default, open_composer/book_paper/plan.py build_plan(min_notional=100.0); not an Alpaca limit",
 "short_min_equity": "$2,000 (margin-and-short-selling doc)",
 "pdt": "FINRA RN 26-10 (2026-04-20) effective 2026-06-04, phase-in to 2027-10-20; Alpaca removed $25k and API fields by 2026-07-06 (blog 2026-04-27)",
}
R["recommendation"] = {"start_tier": 50000, "floor_tier": 25000, "etf_sleeves_as_is_from": 10000, "v12_as_is_from": 250000,
                       "v12_small_capital": "concentrated top-N per side; rounding-feasible N: 100 @25k, 200 @50k, 300 @100k; performance cost untested (task 10-08..10-14)"}
json.dump(R, open("results.json", "w"), indent=1, ensure_ascii=False)
