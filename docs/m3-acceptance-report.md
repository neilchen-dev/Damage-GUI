# M3 验收报告 — 科学验证闭环（消融 / 基线 / 基准 / 不确定度 / 追踪 / 生命周期 / 属性测试 / drift）

日期：2026-09-02 ｜ 版本：2.1.0 ｜ 前置：M1/M2 已冻结，本轮零 GUI 改动、零核心算法口径改动、未启动 P2

M3 目标 = **科学验证闭环**：为已在 M1/M2 完成工程化（双平台 CI、追溯链、数值回归）的
预测系统补齐"科学证据链"——外部基线对照、消融归因、性能基准、样本级不确定度、实验追踪、
模型生命周期、property-based 测试、数据漂移检测。原则贯彻"**代码越少越好，证据越强越好**"，
不为显得专业而制造不存在的问题；负结果如实入库。

---

## 1. P0 工程修复（M3 前置，已完成）

| 项 | 内容 | 验证 |
|---|---|---|
| P0-1 | RBF 数值防护：`RBFInterpolator` 奇异/病态时抛结构化 `ModelFitError`，并暴露 `epsilon`/`smoothing` 实验参数 | `tests/test_rbf_numerical_guard.py` |
| P0-2 | 评估口径统一：raw（已完成双边滤波预处理、但未施加评估阶段高斯平滑）与 smoothed（双边滤波后）**并列输出**，杜绝只报有利口径 | 结果表新增 `MeanRE(raw)` 列 |

两项均为**防护与透明度**，未改动任何数值算法口径；黄金回归容差未动（见 §6）。

---

## 2. M3.1–M3.8 交付清单

框架代码集中在 `src/damage_gui/experiments/`，CLI 在 `scripts/`，**未新建抽象层、未引入外部服务**：

| 里程碑 | 模块 | 脚本/CLI | 测试 |
|---|---|---|---|
| M3.1 消融框架 | `experiments/runner.py` | `scripts/run_experiments.py` | `tests/test_experiments.py` |
| M3.2 外部基线 | `experiments/baselines.py`（nn + linear） | 并入 runner | `tests/test_baselines.py` |
| M3.3 性能基准 | `experiments/benchmark.py` | `scripts/benchmark.py` | `tests/test_benchmark.py` |
| M3.4 不确定度 | `experiments/uncertainty.py` | `scripts/uncertainty_study.py` | `tests/test_uncertainty.py` |
| M3.5 实验追踪 | `experiments/tracking.py`（SQLite） | `scripts/experiment.py` | `tests/test_tracking.py` |
| M3.6 生命周期 | `model/lifecycle.py`（DRAFT→VALIDATED→ACTIVE→ARCHIVED） | `scripts/model_lifecycle.py` | `tests/test_lifecycle.py` |
| M3.7 属性测试 | — | — | `tests/test_properties.py`（Hypothesis） |
| M3.8 漂移检测 | `experiments/drift.py`（KS 检验，轻量） | `scripts/drift_report.py` | `tests/test_drift.py` |

**明确不引入**（守红线）：Redis / Celery / MLflow / 深度学习框架 / 微服务。追踪用标准库
`sqlite3`，漂移用 `scipy.stats` KS 检验，属性测试用 `hypothesis`——全部是已有依赖或轻量测试依赖
（`pyproject.toml [project.optional-dependencies].test`）。

---

## 3. 真实数据运行（Task #11，已完成）

**数据**：本机 `dist/data`（不入 git），F/M/P 各 120 工况，5 高度 × 4 速度 × 6 角度完整因子网格，
`DamageMatrix_*` 为 GBK 文本 + 同名 `.ppm`。

**编排**：脱离会话的后台 orchestrator（`.workbuddy/realdata_runs/run_rest.sh`）逐级串行，
避免 CPU 争用污染 `train_time_seconds` 可比性。运行日志 `===== 2026-09-02 14:36:43 ALL DONE =====`。

> **代码状态与 commit 指针说明（封版审计补充，2026-09-07）**：M3 实验产物生成于
> `b6803e2` 检出基线叠加当时尚未提交的工作区代码（M3 框架 `src/damage_gui/experiments/`、
> `model/lifecycle.py`、9 个测试文件，以及对 `rbf.py / pod.py / bundle.py / metrics.py /
> config.py / errors.py / metadata.py` 的 P0-1 数值防护与 epsilon 透传修改）。
> 因此产物头部与 SQLite 各行记录的 `git_commit=b6803e2` 指向的是**检出基线**而非包含
> M3 代码的 commit。该工作区已由封版 commit **原样收编，未做任何 scientific 改动**
> （黄金容差、87 行实验记录、评估口径均未触碰）；复现与引用以封版 commit 为准。

**落盘产物**（每份 md/json 头部含 生成时间UTC / 数据目录 / 等级 / 种子42 / commit b6803e2 / 训练数据指纹）：

| 目录 | 内容 | 数量 |
|---|---|---|
| `examples/results/experiments/` | `ablation_{F,M,P}_{design,baseline,validation,pod,rbf,rbf_multiquadric}.{csv,json,md}` + `experiments.sqlite3` | 54 份 + 1 库 |
| `examples/results/uncertainty/` | `uncertainty_{F,M,P}_rbf.{csv,json,md}` + `_reliability.png` | 12 份 |
| `examples/results/benchmark/` | `benchmark_{F,M,P}.{csv,json,md}` | 9 份 |

**实验追踪**：`experiments.sqlite3` 表 `experiments` 共 **87 行**（核心矩阵 63 + multiquadric ε 补跑 24），
核心按等级 `[(F,21),(M,21),(P,21)]`，每级 21 = design 4 + baseline 2 + validation 5 + pod 6 + rbf 4，与产物一一对应；
补跑为每级 8 行（suite=`rbf_multiquadric`，ε×smoothing 网格，新 id 64–87）。状态 `[(ok,81),(error,6)]`，
6 行 error 为原 rbf 套件 multiquadric 缺 epsilon 的历史记录，按 append-only 保留（详见 §7.6 与消融报告 §6）。

**训练数据指纹**（按等级独立，非全局同一 hash）：

| 等级 | sha256 |
|---|---|
| F | `b43d66608bc0000055d52c65cf2ad5fdba4199fe596a56830329294d915def20` |
| M | `6763c6ed9e0c68843a02c837265b17da63ec0f675b5502968284d624c22524aa` |
| P | `13bbd9fdc2d64bf180c6aaac798f854ad564eefa87a0bd4d57e38440a255482a` |

科学结论（生产模型 pod_rbf/align=on/K=20 的三级指标、P 级 R² 塌陷、leave_v_out 负 R²、
外部基线竞争力、multiquadric 配置失败已补跑收口）全部写入四份分项报告，此处不复述：
[模型验证](model-validation-report.md) ｜ [消融](ablation-study.md) ｜
[不确定度](uncertainty-validation.md) ｜ [基准](benchmark-report.md)。

---

## 4. 静态检查与测试

| 检查 | 命令 | 结果 |
|---|---|---|
| ruff | `ruff check .` | **All checks passed!**（ruff 0.16.4，line-length 100 / py310 / E,W,F,I,UP,B） |
| 测试 | `.venv/Scripts/python -m pytest -q` | **236 passed, 436 warnings in 40.06s** |

236 = M2 的 139（含数值回归黄金值对比）+ M3 新增（消融/基线/基准/不确定度/追踪/生命周期/
drift 单测 + 12 个 Hypothesis 属性测试）。测试在 CPU 密集的真实数据长跑**全部结束后**才运行，
计时与结果不受争用影响。

> ruff 为用户级安装（PATH 上的 Python 3.12 Scripts），不在 `.venv` 内；以裸 `ruff check .` 运行，
> `python -m ruff` 不可用——已记入项目备忘，避免下次误判为环境问题。

---

## 5. 数值回归（黄金值）纪律

M2 建立的黄金回归（`tests/test_numerical_regression.py` + `tests/data/regression_golden.json`）
在 M3 全程**未被触碰**：

- 容差常量维持 **FIELD_TOL = METRIC_TOL = 1e-6、EV_TOL = OOD_TOL = 1e-9**，本轮**零调整**。
- M3 所有新增代码为"旁路观测"（实验/基线/基准/不确定度/追踪/drift），**不进入**
  预测→重建→评估的核心数值路径，故黄金值无需再生成。
- 236 测试含原黄金对比且全绿，即"加了这么多验证代码，核心数值一字未动"的直接证据。

---

## 6. 红线合规自查

| 红线 | 状态 |
|---|---|
| 不改 GUI / 核心算法口径 | ✅ 未触碰 GUI 与预测/重建/评估算法 |
| 不引入 Redis/Celery/MLflow/深度学习 | ✅ 仅标准库 sqlite3 + scipy KS + hypothesis |
| 不为变绿放宽黄金容差 | ✅ 容差 1e-6/1e-9 零调整（§5） |
| 禁止编造实验数据 | ✅ 全部数字来自 `dist/data` 真实运行产物，文档写作前逐表与磁盘核对 |
| 不改评估口径以美化指标 | ✅ P0-2 反而**增加** raw 口径并列，暴露而非掩盖 |
| 负结果如实报告 | ✅ 见 §7 |
| 每阶段走 10 步闸门、代码越少越好 | ✅ 逐里程碑小步，无 big-bang 重构 |

---

## 7. 如实记录的负结果与已知限制

1. **P 级 R²(sm) 塌陷**：生产模型 0.4460，所有模型皆低（linear 0.3538 / nn 0.1159），
   属数据内禀离散度，**非工程缺陷、不可调参修复**；以 Dice/MeanRE/不确定度并列呈现。
2. **leave_v_out P 级 R²(sm) = -0.6124（负）**：整层抽速度后预测不如均值，硬限制，已写入
   README 与验证报告，不被低 P95 掩盖。
3. **对齐是权衡非增益**：align=on 改善质心/幅值（F MeanRE 0.0870→0.0840、质心 0.1908→0.1838m），
   但 Dice/IoU 变差（0.9101→0.8826 / 0.8387→0.7929），如实报告。
4. **外部简单基线有竞争力**：F/M 级 linear 的 R²(sm) 与生产模型持平、nn 的 Dice/IoU 更高；
   项目价值主张据此校正为"组合优势"而非"单指标领先"。
5. **`knn_distance` 不确定度排序口径失效**：三级 Spearman 仅 0.0619/0.0577/0.0110（规则网格
   输入距离同质），明确不采用；主用同量纲 `residual_knn`（F/M ~0.79、P 0.59）。
6. **multiquadric 核原 `status=error`（配置型失败）已于实验层补跑收口**：真实原因是 scipy 对该核
   **强制要求显式 `epsilon`**，而 runner 默认 `epsilon=(None,)` 未提供；产物 md 附带的
   "改 smoothing 重试"提示不准确（s=0.001 同样报错）。**不影响生产模型**（用 thin_plate_spline）。
   2026-09-02 以一次性 driver 在实验层补 ε 网格 {1.25,2.5,5.0,10.0}×smoothing{0,0.001}（suite
   `rbf_multiquadric`，新 id 64–87，三级 8 spec 全 ok），**未改任何 tracked scientific code**；原 6 行
   error 按 append-only 保留为历史。补跑后 multiquadric 最佳档（ε=1.25,s=0.001）F/M 略优于
   thin_plate_spline，但 **P 级 R² 仍低（最佳 0.502，多臂为负）为确定性负结果**。详见消融报告 §6。
7. **基准为单机单次测量**，PeakMem 为 Python `tracemalloc` 峰值（非进程 RSS）；数值用于同机
   横比与量级判断，换硬件需重跑——口径已在基准报告顶部声明。
8. **遗留清理项（已收口）**：`examples/results/experiments/tracking.sqlite3` 经确认为 0 字节空残留
   （无 `experiments` 表、仅文档散文引用），**已删除**；真实库 `experiments.sqlite3`（87 行）未受影响。
9. **pod_rbf 训练存在 ~1e-4 量级的非确定性（已知可复现性风险，封版轮记录、暂不修复）**：
   生产尺寸训练集（96 工况 × 对齐窗口像素）下，sklearn `PCA(svd_solver="auto")` 解析为
   randomized SVD，而 `PODRBFDamageField.fit`（`model/pod.py`）未固定 `random_state`，
   拟合结果依赖进程内全局随机数状态。实测同进程同配置两次训练的 R²/Dice 波动约
   4e-5 ~ 4e-4（证据：SQLite 中 design 套件 id=46 与 pod 套件 id=57 为同配置两次独立
   训练，指标在第 4~5 位小数不一致；消融报告 §2 与 §5 的 P 级 K=20 双值 0.4460/0.4459
   即此来源）。**影响仅限第 4 位小数，M3 全部科学结论在 1e-3 以上量级成立，不受影响**；
   黄金回归测试的合成数据落在 full-SVD 确定性区间，故未拦截该路径。下一版本优先修复
   （固定 `random_state` 或显式 `svd_solver`），并增加生产尺寸数值回归探针。

---

## 8. 结论与后续

**M3 验收通过**：8 个里程碑全部实现并被 236 个测试覆盖，真实数据 F/M/P 三级 87 组实验
（核心矩阵 63 + multiquadric ε 补跑 24）全部落盘且可追溯（种子/commit/数据指纹），静态检查全绿，
黄金容差零调整，红线零违反，负结果如实入库。项目从"工程完成"推进到"科学证据完成"。

**可选后续（非 M3 目标）**：
1. ~~multiquadric epsilon 网格补全 + rbf 套件重跑~~ **已完成**（§7.6，2026-09-02 实验层补跑收口）；
2. ~~`tracking.sqlite3` 空库清理~~ **已完成**（§7.8，确认空残留后删除）；
3. P2：最小 CLI（info/predict/batch）+ 简历/交付文档收口（唯一剩余可选项）。
4. PCA randomized SVD 随机性修复（固定 `random_state`）+ 生产尺寸黄金回归探针（§7.9，
   下一版本优先；修复会使重跑数值与 87 行库存量记录出现 ~1e-4 量级差异，属预期）。
