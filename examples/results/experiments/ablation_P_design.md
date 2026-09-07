# 实验报告：ablation_P_design

- 生成时间（UTC）: 2026-09-02T04:55:19+00:00
- 数据目录: dist\data
- 等级: P | 随机种子: 42
- 代码 commit: b6803e2
- 训练数据指纹: sha256:13bbd9fdc2d64bf180c6aaac798f854ad564eefa87a0bd4d57e38440a255482a

| Experiment | Status | Model | Validation | Align | K | MeanRE(sm) | P95(sm) | R2(sm) | MeanRE(raw) | Dice | IoU | CentroidErr(m) | Extrap% | Train(s) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| rbf_align=off | ok | rbf | random | off | — | 0.1225 | 0.0893 | 0.4779 | 0.2322 | 0.8495 | 0.7502 | 0.2376 | — | 184.84 |
| rbf_align=on | ok | rbf | random | on | — | 0.1240 | 0.0972 | 0.4415 | 0.2202 | 0.8293 | 0.7189 | 0.2181 | — | 240.66 |
| pod_rbf_align=off | ok | pod_rbf | random | off | 20 | 0.1234 | 0.0903 | 0.4708 | 0.2323 | 0.8593 | 0.7637 | 0.2651 | — | 237.33 |
| pod_rbf_align=on | ok | pod_rbf | random | on | 20 | 0.1235 | 0.0956 | 0.4460 | 0.2205 | 0.8285 | 0.7177 | 0.2177 | — | 254.35 |
