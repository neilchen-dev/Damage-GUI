# 实验报告：ablation_F_rbf_multiquadric

- 生成时间（UTC）: 2026-09-02T08:32:33+00:00
- 数据目录: G:\Damage GUI\dist\data
- 等级: F | 随机种子: 42
- 代码 commit: b6803e2
- 训练数据指纹: sha256:b43d66608bc0000055d52c65cf2ad5fdba4199fe596a56830329294d915def20

| Experiment | Status | Model | Validation | Align | K | MeanRE(sm) | P95(sm) | R2(sm) | MeanRE(raw) | Dice | IoU | CentroidErr(m) | Extrap% | Train(s) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| rbf_multiquadric_s=0_e=1.25 | ok | rbf | random | on | — | 0.1571 | 0.2957 | 0.8373 | 0.1880 | 0.8729 | 0.7773 | 0.3455 | — | 151.76 |
| rbf_multiquadric_s=0_e=2.5 | ok | rbf | random | on | — | 0.1085 | 0.2260 | 0.9092 | 0.1370 | 0.8857 | 0.7978 | 0.2312 | — | 136.53 |
| rbf_multiquadric_s=0_e=5 | ok | rbf | random | on | — | 0.0877 | 0.1900 | 0.9436 | 0.1224 | 0.8822 | 0.7924 | 0.1921 | — | 141.60 |
| rbf_multiquadric_s=0_e=10 | ok | rbf | random | on | — | 0.0841 | 0.1715 | 0.9555 | 0.1197 | 0.8814 | 0.7911 | 0.1823 | — | 154.92 |
| rbf_multiquadric_s=0.001_e=1.25 | ok | rbf | random | on | — | 0.0851 | 0.1681 | 0.9573 | 0.1191 | 0.8823 | 0.7920 | 0.1730 | — | 161.34 |
| rbf_multiquadric_s=0.001_e=2.5 | ok | rbf | random | on | — | 0.1013 | 0.2151 | 0.9206 | 0.1310 | 0.8827 | 0.7929 | 0.2176 | — | 133.00 |
| rbf_multiquadric_s=0.001_e=5 | ok | rbf | random | on | — | 0.0875 | 0.1897 | 0.9439 | 0.1223 | 0.8823 | 0.7925 | 0.1918 | — | 159.04 |
| rbf_multiquadric_s=0.001_e=10 | ok | rbf | random | on | — | 0.0841 | 0.1714 | 0.9555 | 0.1197 | 0.8815 | 0.7911 | 0.1823 | — | 160.45 |
