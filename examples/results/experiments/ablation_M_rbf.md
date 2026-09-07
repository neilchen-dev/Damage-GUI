# 实验报告：ablation_M_rbf

- 生成时间（UTC）: 2026-09-02T04:34:55+00:00
- 数据目录: dist\data
- 等级: M | 随机种子: 42
- 代码 commit: b6803e2
- 训练数据指纹: sha256:6763c6ed9e0c68843a02c837265b17da63ec0f675b5502968284d624c22524aa

| Experiment | Status | Model | Validation | Align | K | MeanRE(sm) | P95(sm) | R2(sm) | MeanRE(raw) | Dice | IoU | CentroidErr(m) | Extrap% | Train(s) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| rbf_thin_plate_spline_s=0 | ok | rbf | random | on | — | 0.0829 | 0.1721 | 0.9454 | 0.1167 | 0.8823 | 0.7921 | 0.1861 | — | 158.92 |
| rbf_thin_plate_spline_s=0.001 | ok | rbf | random | on | — | 0.0828 | 0.1710 | 0.9460 | 0.1166 | 0.8823 | 0.7921 | 0.1859 | — | 137.83 |
| rbf_multiquadric_s=0 | error | rbf | random | on | — | — | — | — | — | — | — | — | — | — |
| rbf_multiquadric_s=0.001 | error | rbf | random | on | — | — | — | — | — | — | — | — | — | — |

## 失败/不适用的实验

- **rbf_multiquadric_s=0**: ModelFitError: 形状插值失败：RBF 方程组奇异或病态（`epsilon` must be specified if `kernel` is not one of {'linear', 'cubic', 'thin_plate_spline', 'quintic'}.）。常见原因：训练工况共线/共面，或精确插值数值不稳定；可将 smoothing 设为略大于 0 的值重试
- **rbf_multiquadric_s=0.001**: ModelFitError: 形状插值失败：RBF 方程组奇异或病态（`epsilon` must be specified if `kernel` is not one of {'linear', 'cubic', 'thin_plate_spline', 'quintic'}.）。常见原因：训练工况共线/共面，或精确插值数值不稳定；可将 smoothing 设为略大于 0 的值重试
