# 实验报告：ablation_F_baseline

- 生成时间（UTC）: 2026-09-02T02:24:08+00:00
- 数据目录: dist\data
- 等级: F | 随机种子: 42
- 代码 commit: b6803e2
- 训练数据指纹: sha256:b43d66608bc0000055d52c65cf2ad5fdba4199fe596a56830329294d915def20

| Experiment | Status | Model | Validation | Align | K | MeanRE(sm) | P95(sm) | R2(sm) | MeanRE(raw) | Dice | IoU | CentroidErr(m) | Extrap% | Train(s) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline_nn | ok | nn | random | on | — | 0.1206 | 0.2358 | 0.9170 | 0.1158 | 0.9439 | 0.8976 | 0.2842 | — | 177.47 |
| baseline_linear | ok | linear | random | on | — | 0.0860 | 0.1835 | 0.9525 | 0.1092 | 0.9308 | 0.8745 | 0.2151 | 0.0833 | 146.38 |
