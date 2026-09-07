# 实验报告：ablation_M_baseline

- 生成时间（UTC）: 2026-09-02T03:14:26+00:00
- 数据目录: dist\data
- 等级: M | 随机种子: 42
- 代码 commit: b6803e2
- 训练数据指纹: sha256:6763c6ed9e0c68843a02c837265b17da63ec0f675b5502968284d624c22524aa

| Experiment | Status | Model | Validation | Align | K | MeanRE(sm) | P95(sm) | R2(sm) | MeanRE(raw) | Dice | IoU | CentroidErr(m) | Extrap% | Train(s) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline_nn | ok | nn | random | on | — | 0.1196 | 0.2253 | 0.9046 | 0.1133 | 0.9439 | 0.8979 | 0.2848 | — | 159.16 |
| baseline_linear | ok | linear | random | on | — | 0.0850 | 0.1820 | 0.9451 | 0.1070 | 0.9306 | 0.8741 | 0.2201 | 0.0833 | 189.69 |
