# T-20260928-10 Stage-1 否定测试：多来源截面排序模型

压力期 2016-05-02 -> 2023-08-31，候选 5/6/11（LightGBM 全层特征）+ B0（价量基线，LightGBM）。

**结论：FAIL**

## 各候选验证集 RankIC（压力期，样本外折）

| 候选 | 说明 | mean RankIC | t | 调仓日数 | 过线 |
|---|---|---:|---:|---:|---|
| B0 | B0 price-volume-only baseline (LightGBM regression, monthly) | 0.0014 | 0.18 | 75 | -- |
| 5 | Candidate 5: LightGBM regression, all layers, monthly, excess_21 | -0.0163 | -0.74 | 45 | FAIL |
| 6 | Candidate 6: LightGBM regression, all layers, biweekly, excess_10 | 0.0032 | 0.21 | 106 | FAIL |
| 11 | Candidate 11: LightGBM LambdaRank, all layers, monthly, excess_21 rank | -0.0172 | -0.76 | 45 | FAIL |

判定线：mean RankIC >= 0.02 且 >= max(0.0071, B0) + 0.01 = 0.0171（B0 = 0.0013701179582589825）。

## 数据层覆盖

- **monthly**：33/45 个特征覆盖率达标（>=50%）保留，12 个因覆盖率 <50% 被自动剔除：
  `short_interest_ratio`(17.2%)、`dtc_change_vs_prior`(17.2%)、`days_to_cover`(17.3%)、
  `dtc_cross_sectional_pct`(17.3%)、`accruals`(26.8%)、`gross_profitability`(28.1%)、
  `sue_rev`(34.5%)、`short_volume_ratio_zscore_21`(38.7%)、`short_volume_ratio`(38.7%)、
  `sue_eps`(39.0%)、`niq_be_chg1`(45.7%)、`niq_at_chg1`(45.8%)。
  `short_interest`/`short_volume` 只覆盖流动性前 1000/500，未按宽池子重建；
  `accruals`/`gross_profitability`/SUE/两个 niq_chg1 因子在宽池子（~8000 只，含大量小盘）
  上 XBRL 覆盖本身就不到一半，如实报告，不是代码 bug。
- **biweekly**：同上，33/45 保留，覆盖率分布与 monthly 基本一致（相差 <0.3pp）。
- **候选 5/6/11 的流动性三档诊断，只有 T1_liquid 有样本**（`results.json` 的
  `by_tercile`）：全层特征逐行 dropna 要求 45 个特征同时非空，短期兴趣/空头成交量
  只覆盖流动性前 1000/500 的名字，结果实际训练+验证样本被收窄到接近纯流动性前 1/3，
  中/低流动性段样本量不足以算出 RankIC——这本身就是"宽池子+空头特征"组合在当前数据
  完整度下的一个真实限制，不是选择性展示。

## 单变量特征 IC 前 5（月度面板，压力期，仅描述）

| 特征 | mean IC | t | 调仓日数 |
|---|---:|---:|---:|
| vol_63 | -0.0880 | -4.78 | 80 |
| idio_vol_63 | -0.0846 | -4.76 | 80 |
| vol_21 | -0.0834 | -4.78 | 80 |
| max_ret_1_21 | -0.0741 | -4.78 | 80 |
| dist_from_252d_high | 0.0634 | 3.59 | 80 |

## Modal 花费

本任务实测花费（`logs/modal-t20260928-10-*.log`，`actual_cost_usd`）：
smoke 三次 $0.0019+$0.0041+$0.0094 + 正式跑 $0.2105 = **约 $0.226**，
在 ≤$1.2 预算内。账户本月累计（`python3 scripts/modal_budget.py status`，含其他会话任务）：
billed $1.3296，projected $6.1835，月上限 $25。

## 结论

候选 5、6、11 在压力期（2016-05-02 → 2023-08-31）验证集 RankIC 均未达到
`>=0.02` 且 `>=max(0.0071, B0)+0.01=0.0171` 的双门槛；候选 5、11 甚至为负
（-0.0163、-0.0172），候选 6 为 0.0032，均明显低于门槛。同价量特征的岭回归基线
（H-20260917-02，0.0071）本身也未被这次的 LightGBM 全层模型超过。
**Stage-1 否定；不进入 Stage-2（≤$3 完整评估）。**

