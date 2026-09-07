# 实验报告：ablation_M_design

- 生成时间（UTC）: 2026-09-02T03:08:34+00:00
- 数据目录: dist\data
- 等级: M | 随机种子: 42
- 代码 commit: b6803e2
- 训练数据指纹: sha256:6763c6ed9e0c68843a02c837265b17da63ec0f675b5502968284d624c22524aa

| Experiment | Status | Model | Validation | Align | K | MeanRE(sm) | P95(sm) | R2(sm) | MeanRE(raw) | Dice | IoU | CentroidErr(m) | Extrap% | Train(s) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| rbf_align=off | ok | rbf | random | off | — | 0.0859 | 0.1696 | 0.9474 | 0.1257 | 0.9105 | 0.8394 | 0.1922 | — | 119.54 |
| rbf_align=on | ok | rbf | random | on | — | 0.0829 | 0.1721 | 0.9454 | 0.1167 | 0.8823 | 0.7921 | 0.1861 | — | 116.21 |
| pod_rbf_align=off | ok | pod_rbf | random | off | 20 | 0.0866 | 0.1639 | 0.9507 | 0.1323 | 0.9050 | 0.8297 | 0.2337 | — | 186.82 |
| pod_rbf_align=on | ok | pod_rbf | random | on | 20 | 0.0825 | 0.1695 | 0.9462 | 0.1195 | 0.8805 | 0.7893 | 0.1857 | — | 165.59 |
