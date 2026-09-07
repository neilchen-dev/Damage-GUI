# 实验报告：ablation_P_pod

- 生成时间（UTC）: 2026-09-02T05:45:39+00:00
- 数据目录: dist\data
- 等级: P | 随机种子: 42
- 代码 commit: b6803e2
- 训练数据指纹: sha256:13bbd9fdc2d64bf180c6aaac798f854ad564eefa87a0bd4d57e38440a255482a

| Experiment | Status | Model | Validation | Align | K | MeanRE(sm) | P95(sm) | R2(sm) | MeanRE(raw) | Dice | IoU | CentroidErr(m) | Extrap% | Train(s) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pod_K=5 | ok | pod_rbf | random | on | 5 | 0.1235 | 0.0968 | 0.4486 | 0.2301 | 0.8189 | 0.7028 | 0.2177 | — | 203.71 |
| pod_K=10 | ok | pod_rbf | random | on | 10 | 0.1203 | 0.0955 | 0.4641 | 0.2232 | 0.8265 | 0.7142 | 0.2173 | — | 186.53 |
| pod_K=15 | ok | pod_rbf | random | on | 15 | 0.1231 | 0.0957 | 0.4478 | 0.2220 | 0.8269 | 0.7149 | 0.2170 | — | 190.35 |
| pod_K=20 | ok | pod_rbf | random | on | 20 | 0.1235 | 0.0956 | 0.4459 | 0.2205 | 0.8283 | 0.7174 | 0.2177 | — | 229.41 |
| pod_K=25 | ok | pod_rbf | random | on | 25 | 0.1240 | 0.0971 | 0.4421 | 0.2204 | 0.8287 | 0.7181 | 0.2179 | — | 207.23 |
| pod_K=30 | ok | pod_rbf | random | on | 30 | 0.1242 | 0.0969 | 0.4396 | 0.2209 | 0.8293 | 0.7193 | 0.2178 | — | 323.72 |
