# 实验报告：ablation_F_validation

- 生成时间（UTC）: 2026-09-02T02:36:31+00:00
- 数据目录: dist\data
- 等级: F | 随机种子: 42
- 代码 commit: b6803e2
- 训练数据指纹: sha256:b43d66608bc0000055d52c65cf2ad5fdba4199fe596a56830329294d915def20

| Experiment | Status | Model | Validation | Align | K | MeanRE(sm) | P95(sm) | R2(sm) | MeanRE(raw) | Dice | IoU | CentroidErr(m) | Extrap% | Train(s) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| validation_random | ok | pod_rbf | random | on | 20 | 0.0844 | 0.1735 | 0.9539 | 0.1221 | 0.8798 | 0.7885 | 0.1838 | — | 141.01 |
| validation_leave_h_out | ok | pod_rbf | leave_h_out | on | 20 | 0.0923 | 0.1726 | 0.9542 | 0.1312 | 0.8760 | 0.7815 | 0.1772 | — | 155.79 |
| validation_leave_v_out | ok | pod_rbf | leave_v_out | on | 20 | 0.1517 | 0.2411 | 0.8922 | 0.1992 | 0.8584 | 0.7549 | 0.6396 | — | 157.54 |
| validation_leave_deg_out | ok | pod_rbf | leave_deg_out | on | 20 | 0.0812 | 0.1653 | 0.9588 | 0.1255 | 0.8789 | 0.7868 | 0.1501 | — | 142.42 |
| validation_corner | ok | pod_rbf | corner | on | 20 | 0.1039 | 0.2075 | 0.9406 | 0.1201 | 0.8517 | 0.7425 | 0.2695 | — | 145.87 |
