# 不确定度校准报告：uncertainty_P_rbf

- 生成时间（UTC）: 2026-09-02T06:01:26+00:00
- 数据目录: dist\data | 等级: P | 模型: rbf | 样本数: 120 | k: 3
- 样本平均误差（Smoothed ROI MAE）: 0.0003

## Spearman 秩相关（估计值 vs 实际误差）

- knn_distance（排序口径）: 0.0110
- residual_knn（同量纲）: 0.5912

## 校准分箱（residual_knn，同量纲）

| bin | n | mean_estimate | mean_error |
|---|---|---|---|
| 0 | 30 | 0.0002 | 0.0002 |
| 1 | 30 | 0.0003 | 0.0003 |
| 2 | 30 | 0.0004 | 0.0004 |
| 3 | 30 | 0.0005 | 0.0005 |

## 校准分箱（knn_distance，排序口径）

| bin | n | mean_estimate | mean_error |
|---|---|---|---|
| 0 | 120 | 0.2594 | 0.0003 |

可靠性曲线: uncertainty_P_rbf_reliability.png

方法说明：LOO 残差（Smoothed 口径 ROI MAE）+ kNN 估计；对样本 i 的估计只用其余样本构建。Bootstrap 残差需 B 次重训，与轻量定位不符，未采用。若相关系数接近 0 或分箱无单调趋势，说明该估计器对当前数据不可靠，应如实报告而非调参掩盖。
