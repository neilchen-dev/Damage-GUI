# 实验报告：ablation_P_baseline

- 生成时间（UTC）: 2026-09-02T05:03:08+00:00
- 数据目录: dist\data
- 等级: P | 随机种子: 42
- 代码 commit: b6803e2
- 训练数据指纹: sha256:13bbd9fdc2d64bf180c6aaac798f854ad564eefa87a0bd4d57e38440a255482a

| Experiment | Status | Model | Validation | Align | K | MeanRE(sm) | P95(sm) | R2(sm) | MeanRE(raw) | Dice | IoU | CentroidErr(m) | Extrap% | Train(s) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline_nn | ok | nn | random | on | — | 0.1419 | 0.1283 | 0.1159 | 0.1932 | 0.8811 | 0.8043 | 0.3067 | — | 247.90 |
| baseline_linear | ok | linear | random | on | — | 0.1273 | 0.1018 | 0.3538 | 0.2092 | 0.8659 | 0.7781 | 0.2747 | 0.0833 | 220.55 |
