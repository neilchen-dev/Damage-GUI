# 实验报告：ablation_M_validation

- 生成时间（UTC）: 2026-09-02T03:32:09+00:00
- 数据目录: dist\data
- 等级: M | 随机种子: 42
- 代码 commit: b6803e2
- 训练数据指纹: sha256:6763c6ed9e0c68843a02c837265b17da63ec0f675b5502968284d624c22524aa

| Experiment | Status | Model | Validation | Align | K | MeanRE(sm) | P95(sm) | R2(sm) | MeanRE(raw) | Dice | IoU | CentroidErr(m) | Extrap% | Train(s) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| validation_random | ok | pod_rbf | random | on | 20 | 0.0825 | 0.1695 | 0.9462 | 0.1195 | 0.8804 | 0.7892 | 0.1857 | — | 213.41 |
| validation_leave_h_out | ok | pod_rbf | leave_h_out | on | 20 | 0.0913 | 0.1717 | 0.9454 | 0.1298 | 0.8768 | 0.7827 | 0.1979 | — | 221.75 |
| validation_leave_v_out | ok | pod_rbf | leave_v_out | on | 20 | 0.1484 | 0.2329 | 0.8793 | 0.1975 | 0.8587 | 0.7555 | 0.6713 | — | 221.58 |
| validation_leave_deg_out | ok | pod_rbf | leave_deg_out | on | 20 | 0.0801 | 0.1622 | 0.9520 | 0.1251 | 0.8782 | 0.7857 | 0.1532 | — | 230.27 |
| validation_corner | ok | pod_rbf | corner | on | 20 | 0.1017 | 0.2056 | 0.9316 | 0.1204 | 0.8520 | 0.7429 | 0.2806 | — | 174.40 |
