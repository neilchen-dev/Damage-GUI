# 实验报告：ablation_F_rbf

- 生成时间（UTC）: 2026-09-02T02:58:42+00:00
- 数据目录: dist\data
- 等级: F | 随机种子: 42
- 代码 commit: b6803e2
- 训练数据指纹: sha256:b43d66608bc0000055d52c65cf2ad5fdba4199fe596a56830329294d915def20

| Experiment | Status | Model | Validation | Align | K | MeanRE(sm) | P95(sm) | R2(sm) | MeanRE(raw) | Dice | IoU | CentroidErr(m) | Extrap% | Train(s) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| rbf_thin_plate_spline_s=0 | ok | rbf | random | on | — | 0.0840 | 0.1760 | 0.9533 | 0.1192 | 0.8826 | 0.7929 | 0.1840 | — | 148.13 |
| rbf_thin_plate_spline_s=0.001 | ok | rbf | random | on | — | 0.0839 | 0.1749 | 0.9539 | 0.1191 | 0.8819 | 0.7920 | 0.1836 | — | 124.89 |
| rbf_multiquadric_s=0 | error | rbf | random | on | — | — | — | — | — | — | — | — | — | — |
| rbf_multiquadric_s=0.001 | error | rbf | random | on | — | — | — | — | — | — | — | — | — | — |

## 失败/不适用的实验

- **rbf_multiquadric_s=0**: ModelFitError: 形状插值失败：RBF 方程组奇异或病态（`epsilon` must be specified if `kernel` is not one of {'thin_plate_spline', 'quintic', 'cubic', 'linear'}.）。常见原因：训练工况共线/共面，或精确插值数值不稳定；可将 smoothing 设为略大于 0 的值重试
- **rbf_multiquadric_s=0.001**: ModelFitError: 形状插值失败：RBF 方程组奇异或病态（`epsilon` must be specified if `kernel` is not one of {'thin_plate_spline', 'quintic', 'cubic', 'linear'}.）。常见原因：训练工况共线/共面，或精确插值数值不稳定；可将 smoothing 设为略大于 0 的值重试
