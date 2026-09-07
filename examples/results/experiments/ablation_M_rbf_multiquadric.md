# 实验报告：ablation_M_rbf_multiquadric

- 生成时间（UTC）: 2026-09-02T08:51:58+00:00
- 数据目录: G:\Damage GUI\dist\data
- 等级: M | 随机种子: 42
- 代码 commit: b6803e2
- 训练数据指纹: sha256:6763c6ed9e0c68843a02c837265b17da63ec0f675b5502968284d624c22524aa

| Experiment | Status | Model | Validation | Align | K | MeanRE(sm) | P95(sm) | R2(sm) | MeanRE(raw) | Dice | IoU | CentroidErr(m) | Extrap% | Train(s) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| rbf_multiquadric_s=0_e=1.25 | ok | rbf | random | on | — | 0.1549 | 0.2899 | 0.8115 | 0.1849 | 0.8734 | 0.7778 | 0.3533 | — | 145.55 |
| rbf_multiquadric_s=0_e=2.5 | ok | rbf | random | on | — | 0.1067 | 0.2207 | 0.8948 | 0.1336 | 0.8881 | 0.8008 | 0.2348 | — | 142.18 |
| rbf_multiquadric_s=0_e=5 | ok | rbf | random | on | — | 0.0865 | 0.1838 | 0.9342 | 0.1193 | 0.8838 | 0.7945 | 0.1932 | — | 151.19 |
| rbf_multiquadric_s=0_e=10 | ok | rbf | random | on | — | 0.0831 | 0.1684 | 0.9479 | 0.1169 | 0.8822 | 0.7921 | 0.1854 | — | 128.24 |
| rbf_multiquadric_s=0.001_e=1.25 | ok | rbf | random | on | — | 0.0840 | 0.1661 | 0.9500 | 0.1166 | 0.8823 | 0.7917 | 0.1749 | — | 140.49 |
| rbf_multiquadric_s=0.001_e=2.5 | ok | rbf | random | on | — | 0.1000 | 0.2124 | 0.9073 | 0.1279 | 0.8854 | 0.7965 | 0.2191 | — | 145.79 |
| rbf_multiquadric_s=0.001_e=5 | ok | rbf | random | on | — | 0.0864 | 0.1837 | 0.9346 | 0.1192 | 0.8840 | 0.7948 | 0.1929 | — | 145.34 |
| rbf_multiquadric_s=0.001_e=10 | ok | rbf | random | on | — | 0.0831 | 0.1683 | 0.9480 | 0.1169 | 0.8822 | 0.7921 | 0.1854 | — | 164.88 |
