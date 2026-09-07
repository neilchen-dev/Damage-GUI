# 不确定度校准报告：uncertainty_M_rbf

- 生成时间（UTC）: 2026-09-02T04:39:55+00:00
- 数据目录: dist\data | 等级: M | 模型: rbf | 样本数: 120 | k: 3
- 样本平均误差（Smoothed ROI MAE）: 0.0017

## Spearman 秩相关（估计值 vs 实际误差）

- knn_distance（排序口径）: 0.0577
- residual_knn（同量纲）: 0.7843

## 校准分箱（residual_knn，同量纲）

| bin | n | mean_estimate | mean_error |
|---|---|---|---|
| 0 | 30 | 0.0008 | 0.0008 |
| 1 | 30 | 0.0013 | 0.0013 |
| 2 | 30 | 0.0019 | 0.0021 |
| 3 | 30 | 0.0027 | 0.0027 |

## 校准分箱（knn_distance，排序口径）

| bin | n | mean_estimate | mean_error |
|---|---|---|---|
| 0 | 120 | 0.2594 | 0.0017 |

可靠性曲线: uncertainty_M_rbf_reliability.png

方法说明：LOO 残差（Smoothed 口径 ROI MAE）+ kNN 估计；对样本 i 的估计只用其余样本构建。Bootstrap 残差需 B 次重训，与轻量定位不符，未采用。若相关系数接近 0 或分箱无单调趋势，说明该估计器对当前数据不可靠，应如实报告而非调参掩盖。
