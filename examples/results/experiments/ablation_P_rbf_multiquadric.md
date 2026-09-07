# 实验报告：ablation_P_rbf_multiquadric

- 生成时间（UTC）: 2026-09-02T09:12:20+00:00
- 数据目录: G:\Damage GUI\dist\data
- 等级: P | 随机种子: 42
- 代码 commit: b6803e2
- 训练数据指纹: sha256:13bbd9fdc2d64bf180c6aaac798f854ad564eefa87a0bd4d57e38440a255482a

| Experiment | Status | Model | Validation | Align | K | MeanRE(sm) | P95(sm) | R2(sm) | MeanRE(raw) | Dice | IoU | CentroidErr(m) | Extrap% | Train(s) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| rbf_multiquadric_s=0_e=1.25 | ok | rbf | random | on | — | 0.3021 | 0.2024 | -2.17 | 0.3510 | 0.7361 | 0.6016 | 0.4899 | — | 141.74 |
| rbf_multiquadric_s=0_e=2.5 | ok | rbf | random | on | — | 0.1777 | 0.1619 | -0.2707 | 0.2631 | 0.8004 | 0.6814 | 0.2793 | — | 145.50 |
| rbf_multiquadric_s=0_e=5 | ok | rbf | random | on | — | 0.1304 | 0.1147 | 0.3297 | 0.2314 | 0.8207 | 0.7071 | 0.2208 | — | 142.29 |
| rbf_multiquadric_s=0_e=10 | ok | rbf | random | on | — | 0.1245 | 0.0942 | 0.4574 | 0.2221 | 0.8274 | 0.7167 | 0.2187 | — | 164.36 |
| rbf_multiquadric_s=0.001_e=1.25 | ok | rbf | random | on | — | 0.1219 | 0.0851 | 0.5022 | 0.2123 | 0.8294 | 0.7196 | 0.2006 | — | 157.88 |
| rbf_multiquadric_s=0.001_e=2.5 | ok | rbf | random | on | — | 0.1623 | 0.1451 | -0.0644 | 0.2518 | 0.8152 | 0.7013 | 0.2555 | — | 152.53 |
| rbf_multiquadric_s=0.001_e=5 | ok | rbf | random | on | — | 0.1301 | 0.1142 | 0.3338 | 0.2310 | 0.8210 | 0.7075 | 0.2206 | — | 149.77 |
| rbf_multiquadric_s=0.001_e=10 | ok | rbf | random | on | — | 0.1244 | 0.0942 | 0.4576 | 0.2220 | 0.8274 | 0.7167 | 0.2187 | — | 166.70 |
