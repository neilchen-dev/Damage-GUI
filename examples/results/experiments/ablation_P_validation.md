# 实验报告：ablation_P_validation

- 生成时间（UTC）: 2026-09-02T05:23:16+00:00
- 数据目录: dist\data
- 等级: P | 随机种子: 42
- 代码 commit: b6803e2
- 训练数据指纹: sha256:13bbd9fdc2d64bf180c6aaac798f854ad564eefa87a0bd4d57e38440a255482a

| Experiment | Status | Model | Validation | Align | K | MeanRE(sm) | P95(sm) | R2(sm) | MeanRE(raw) | Dice | IoU | CentroidErr(m) | Extrap% | Train(s) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| validation_random | ok | pod_rbf | random | on | 20 | 0.1235 | 0.0956 | 0.4460 | 0.2205 | 0.8285 | 0.7177 | 0.2177 | — | 234.68 |
| validation_leave_h_out | ok | pod_rbf | leave_h_out | on | 20 | 0.1437 | 0.1045 | 0.2789 | 0.2294 | 0.8253 | 0.7103 | 0.3138 | — | 279.14 |
| validation_leave_v_out | ok | pod_rbf | leave_v_out | on | 20 | 0.2373 | 0.1421 | -0.6124 | 0.3732 | 0.7280 | 0.5857 | 0.7011 | — | 221.67 |
| validation_leave_deg_out | ok | pod_rbf | leave_deg_out | on | 20 | 0.1042 | 0.0783 | 0.6254 | 0.2092 | 0.8376 | 0.7296 | 0.2233 | — | 238.12 |
| validation_corner | ok | pod_rbf | corner | on | 20 | 0.1949 | 0.1182 | 0.1520 | 0.2955 | 0.8130 | 0.6873 | 0.4227 | — | 232.49 |
