# 实验报告：ablation_P_rbf

- 生成时间（UTC）: 2026-09-02T05:55:25+00:00
- 数据目录: dist\data
- 等级: P | 随机种子: 42
- 代码 commit: b6803e2
- 训练数据指纹: sha256:13bbd9fdc2d64bf180c6aaac798f854ad564eefa87a0bd4d57e38440a255482a

| Experiment | Status | Model | Validation | Align | K | MeanRE(sm) | P95(sm) | R2(sm) | MeanRE(raw) | Dice | IoU | CentroidErr(m) | Extrap% | Train(s) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| rbf_thin_plate_spline_s=0 | ok | rbf | random | on | — | 0.1240 | 0.0972 | 0.4415 | 0.2202 | 0.8293 | 0.7189 | 0.2181 | — | 167.07 |
| rbf_thin_plate_spline_s=0.001 | ok | rbf | random | on | — | 0.1239 | 0.0958 | 0.4471 | 0.2197 | 0.8292 | 0.7189 | 0.2180 | — | 159.24 |
| rbf_multiquadric_s=0 | error | rbf | random | on | — | — | — | — | — | — | — | — | — | — |
| rbf_multiquadric_s=0.001 | error | rbf | random | on | — | — | — | — | — | — | — | — | — | — |

## 失败/不适用的实验

- **rbf_multiquadric_s=0**: ModelFitError: 形状插值失败：RBF 方程组奇异或病态（`epsilon` must be specified if `kernel` is not one of {'quintic', 'linear', 'cubic', 'thin_plate_spline'}.）。常见原因：训练工况共线/共面，或精确插值数值不稳定；可将 smoothing 设为略大于 0 的值重试
- **rbf_multiquadric_s=0.001**: ModelFitError: 形状插值失败：RBF 方程组奇异或病态（`epsilon` must be specified if `kernel` is not one of {'quintic', 'linear', 'cubic', 'thin_plate_spline'}.）。常见原因：训练工况共线/共面，或精确插值数值不稳定；可将 smoothing 设为略大于 0 的值重试
