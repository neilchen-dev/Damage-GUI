# 实验报告：ablation_F_design

- 生成时间（UTC）: 2026-09-01T10:35:04+00:00
- 数据目录: dist\data
- 等级: F | 随机种子: 42
- 代码 commit: b6803e2
- 训练数据指纹: sha256:b43d66608bc0000055d52c65cf2ad5fdba4199fe596a56830329294d915def20

| Experiment | Status | Model | Validation | Align | K | MeanRE(sm) | P95(sm) | R2(sm) | MeanRE(raw) | Dice | IoU | CentroidErr(m) | Extrap% | Train(s) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| rbf_align=off | ok | rbf | random | off | — | 0.0870 | 0.1749 | 0.9544 | 0.1275 | 0.9101 | 0.8387 | 0.1908 | — | 201.34 |
| rbf_align=on | ok | rbf | random | on | — | 0.0840 | 0.1760 | 0.9533 | 0.1192 | 0.8826 | 0.7929 | 0.1840 | — | 222.27 |
| pod_rbf_align=off | ok | pod_rbf | random | off | 20 | 0.0882 | 0.1693 | 0.9567 | 0.1337 | 0.9049 | 0.8299 | 0.2298 | — | 162.86 |
| pod_rbf_align=on | ok | pod_rbf | random | on | 20 | 0.0844 | 0.1735 | 0.9539 | 0.1221 | 0.8798 | 0.7885 | 0.1838 | — | 168.55 |
