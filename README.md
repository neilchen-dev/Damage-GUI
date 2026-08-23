# 基于数据驱动的毁伤场快速预测系统

这是一个面向仿真毁伤数据的 Python 桌面工具：根据飞行/撞击工况重建二维毁伤场，并提供精度评估、可信度检测、可视化和瞄准点优化能力。

**英文定位**：Centroid-Aligned POD-RBF Surrogate Model for Fast Reconstruction and Assessment of High-Dimensional Damage Fields

## 问题与目标

输入为工况参数 `(h, v, deg)` 与毁伤等级（`F`、`M`、`P`），输出为连续的 `473 × 473` 二维毁伤场，而非单一数值。

由于毁伤图案会随工况发生空间位移，直接逐像素插值容易产生图案淡化或重影。本项目将图案形状与空间平移分离后分别建模，以提升场重建质量。

## 方法流程

```text
仿真 DamageMatrix 数据
        → 双边滤波降噪（保留毁伤峰值与边缘）
        → 质心提取与对齐（形状与平移解耦，消除插值重影）
        → POD / PCA 降阶（K 个空间模态，可选）
        → RBF 在 (h, v, deg) 空间插值形状/模态系数与质心
        → 质心恢复 → 二维毁伤场预测
        → 精度评估（数值 + 空间双维度）/ OOD 可信度检测 / 瞄准优化
```

### 核心算法设计

- **双边滤波降噪**：只平滑数值相近的邻域，毁伤核心峰值（~1.0）完整保留（高斯平滑会把峰值压到 0.38，已弃用）。
- **质心对齐插值**：先把各工况图案平移到质心居中的标准位置再插值形状，质心轨迹单独插值——图案的移动被显式建模，消除"重影"。该设计通过合成移动高斯场实验验证（见 `tests/test_alignment.py`）。
- **POD-RBF 降阶模型**（可选）：利用毁伤场的空间相关性做 POD 降维，RBF 只需预测 K=10~30 维模态系数而非上万维像素，项目从"RBF 插值 GUI"升级为 **Reduced Order Model / Surrogate Modeling 系统**。
- **结构化交叉验证**：随机留出之外，支持按高度/速度/角度整层留出与角落区域留出——检验模型在"真正未见过的工况区域"上的可靠性，而非只在随机插值条件下表现良好。
- **OOD / 预测可信度检测**：组合最近训练工况距离、SVD 内在维度全局凸包与局部邻域凸包。SVD 可处理任意方向的共面/共线数据并拒绝偏离训练子空间的查询；局部凸包补充全局凸包无法表达凹形支撑域的缺陷，可把密集 L 形分布内部的数据空洞从 High 降为 Medium。GUI 会明确显示“全局凸包外”或“局部训练支撑不足”。
- **Raw / Smoothed 双口径评估**：同时报告逐像素口径与局部平均场口径指标，说明平滑口径的统计含义，避免"通过平滑刷指标"的质疑。
- **二维空间场指标**：质心误差、峰值位置/强度误差、IoU、Dice——覆盖空间位置与毁伤区域形状的评价维度。
- **瞄准点优化**：基于 CEP 或 REP/DEP 概率散布模型的价值场卷积 + argmax 最优瞄准点。支持完整协方差散布——相关系数 ρ ∈ (−1, 1) 的相关高斯核，以及 REP 主轴相对 x 轴旋转任意角度 θ 的散布椭圆（协方差矩阵参数化）。`monte_carlo_expected_damage` 提供落点采样的 Monte Carlo 独立验证：与解析卷积走不同数学路径，二者在统计容差内一致即可互证实现正确性（`tests/test_aim_correlation.py`）。

## 项目结构

```text
.
├── src/damage_gui/
│   ├── app.py                 # 应用入口（瘦启动器 + 向后兼容 re-export）
│   ├── config.py              # 全局配置（模型 / 预处理 / 评估 / UI）
│   ├── data/
│   │   ├── loader.py          # 工况解析与 DamageMatrix 读取
│   │   └── preprocessing.py   # 双边滤波、ROI、坐标网格、评估口径平滑
│   ├── model/
│   │   ├── rbf.py             # 质心对齐 RBF 插值场
│   │   ├── pod.py             # POD-RBF 降阶代理模型
│   │   ├── validation.py      # 结构化交叉验证切分
│   │   ├── ood.py             # OOD / 预测可信度检测
│   │   └── bundle.py          # 训练编排、评估与模型包（ModelBundle）
│   ├── evaluation/
│   │   └── metrics.py         # 数值指标 + 空间场指标（质心/峰值/IoU/Dice）
│   ├── optimization/
│   │   └── aim.py             # 瞄准点优化（独立数学模块）
│   ├── visualization/
│   │   └── plots.py           # 热力图与误差场渲染
│   └── gui/
│       ├── main_window.py     # Tkinter 主窗口（后台线程训练）
│       ├── presentation.py    # 选项映射与指标展示文案
│       ├── resources.py       # 源码/打包双模式资源路径
│       └── widgets.py         # 通用小部件工具
├── scripts/
│   ├── build.bat              # 常规 PyInstaller 构建脚本
│   ├── build_release.bat      # 轻量版 Windows 发布构建脚本
│   ├── generate_results.py    # 从本地数据复现示例结果
│   ├── ablation_study.py      # 消融实验（降噪/对齐/POD 各自的贡献）
│   ├── validation_study.py    # 五种结构化验证汇总表
│   └── pod_sweep.py           # POD 模态数 K 扫描与性能对比
├── tests/                     # 可重复运行的数值、指标与端到端测试
├── .github/workflows/test.yml # CI（Windows + Ubuntu，Python 3.11）
├── pyproject.toml             # 包元数据与依赖版本范围
├── LICENSE                    # MIT License
├── requirements.txt
└── README.md
```

仿真矩阵、训练模型、虚拟环境和打包产物均不纳入 Git。训练前请准备本地 `data/` 目录，文件名需符合：`DamageMatrix_<F|M|P>_h_<h>_v_<v>_deg_<deg>`。

## 快速开始

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:PYTHONPATH = "src"
python -m damage_gui.app
```

启动后，在 GUI 中选择本地数据目录、毁伤等级、模型类型（RBF / POD-RBF）与验证方式，训练或加载模型后即可输入工况进行预测。训练在后台线程执行，可随时取消；预测完成后显示耗时与模型可信度。

## 图形界面

GUI 支持数据目录选择、模型类型与验证方式选择、后台线程训练（可取消）、工况输入、毁伤场可视化、OOD 可信度显示、CSV/PNG 导出以及瞄准点优化（CEP 圆形散布 / REP-DEP 椭圆散布，支持相关系数 ρ 与主轴旋转角 θ 输入，结果摘要显示等效 σx、σy、ρ）。

![毁伤场预测 GUI](examples/screenshots/gui.png)

## 真实示例结果

下图和指标由本机 F 级仿真数据重新生成，采用默认固定随机种子进行 80/20 留出验证。代表性留出工况为 `h=1`、`v=300`、`deg=30`。

| 评价范围 | RMSE | MAE | R² | 平均相对误差 | P95 混合误差 |
|---|---:|---:|---:|---:|---:|
| 全场 | 0.0013 | 0.0001 | 0.9878 | — | — |
| ROI 区域 | 0.0071 | 0.0017 | 0.9864 | — | — |
| 主要毁伤区（`damage > 0.05`） | 0.0203 | 0.0125 | 0.9533 | 8.40% | 17.60% |

![F 级留出工况：真实毁伤场、预测毁伤场与带符号误差](examples/results/f_prediction.png)

完整指标 CSV 与结果摘要见 [`examples/results`](examples/results)。如需复现：

```powershell
$env:PYTHONPATH = "src"
python scripts/generate_results.py --data-dir path\to\data --level F
```

## 结构化验证

随机 80/20 留出对规则工况网格偏乐观（测试点常被训练点包围）。GUI 与服务层支持以下验证方式：

| 验证方式 | 说明 |
|---|---|
| Random Holdout | 随机 80/20 留出（基线，插值口径） |
| Leave-h-out | 每个高度值轮流整层留出，聚合折外预测 |
| Leave-v-out | 每个速度值轮流整层留出 |
| Leave-deg-out | 每个角度值轮流整层留出 |
| Corner Holdout | 高速 + 大角度角落区域整块外推测试（默认 `v >= 250, deg >= 40`） |

整层留出的指标来自"真正未见过的工况区域"上的折外预测；交付模型最终在全部工况上重新训练。

使用本地真实仿真数据一次生成五种验证方式的 Markdown/CSV 汇总表：

```powershell
$env:PYTHONPATH = "src"
python scripts/validation_study.py --data-dir path\to\data --level F
```

默认输出到 `examples/results/validation_summary.md`，包含 Mean RE、P95 Hybrid、R²、IoU、Dice 与训练耗时。仓库不包含私有仿真矩阵，因此不会提交未经真实数据运行的占位数值。

本机 `dist/data` 的 F/M/P 三级真实数据均已完成验证。下表每格为
`Mean RE / P95 Hybrid`：

| 等级 | Random | Leave-h | Leave-v | Leave-deg | Corner |
|---|---:|---:|---:|---:|---:|
| F | 8.40% / 17.60% | 9.19% / 17.24% | 15.28% / 24.40% | 8.10% / 16.57% | 10.08% / 20.82% |
| M | 8.29% / 17.21% | 9.10% / 17.14% | 14.97% / 23.59% | 7.93% / 16.21% | 9.87% / 20.51% |
| P | 12.40% / 9.72% | 14.32% / 10.42% | 23.59% / 14.13% | 10.50% / 7.85% | 19.51% / 11.68% |

完整结果见 [`F`](examples/results/validation_summary.md)、
[`M`](examples/results/validation_summary_M.md)、
[`P`](examples/results/validation_summary_P.md)。三等级都表明速度方向整层外推最困难；
其中 P 级 Leave-v-out 的 R² 为 -0.597，不能因 P95 Hybrid 较低而误判为可靠。

### OOD 阈值校准

可把真实结构化验证误差与归一化工况网格步长配对，复算 OOD 阈值并检查
局部凸包误报：

```powershell
python scripts/calibrate_ood.py `
  --data-dir dist/data `
  --validation-csv examples/results/validation_summary.csv `
  --level F
```

校准要求 Mean RE 与 P95 Hybrid 同时不超过 20%。F/M/P 三级给出的建议值
均为 `high_max=0.150、medium_max=0.292`，项目采用便于解释的工程取整值
`0.15/0.30`。新自动局部邻居规则在固定随机留出的
22 个全局凸包内测试点上，将误报从 4 个降为 0；完整依据见
[`F`](examples/results/ood_calibration.md)、
[`M`](examples/results/ood_calibration_M.md)、
[`P`](examples/results/ood_calibration_P.md)。

## POD 模态数扫描

对 `K=5/10/20/30/50` 比较累计解释方差、模型大小、训练/预测耗时及精度：

```powershell
$env:PYTHONPATH = "src"
python scripts/pod_sweep.py --data-dir path\to\data --level F
```

默认输出 `examples/results/pod_sweep.md` 和对应 CSV。该结果用于选择精度、速度与模型体积之间的平衡点，而不是仅凭经验固定 K。

## 消融实验

量化双边滤波、质心对齐与 POD 降阶各自的贡献：

```powershell
$env:PYTHONPATH = "src"
python scripts/ablation_study.py --data-dir path\to\data --level F
```

输出 Markdown 表格（`examples/results/ablation.md`）对比 Raw RBF / RBF+Denoise / RBF+Alignment / RBF+Full / POD-RBF+Full 的 Mean RE、P95 Hybrid、R² 与训练/预测耗时。质心对齐的贡献同样由合成移动高斯场单元测试（`tests/test_alignment.py`）验证：对齐模型恢复正确的移动图案，未对齐模型出现图案重影。

## 测试与 CI

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

测试覆盖：

- 散布参数转换（CEP / REP-DEP → σ）、概率核归一化、零散布极限
- 相关散布核（ρ ≠ 0）：归一化、马氏截断、方向性、ρ=0 一致性
- 旋转椭圆协方差参数化：三角恒等式、方差旋转不变性、轴交换
- Monte Carlo 期望毁伤效能 vs 解析卷积的一致性（独立/相关散布两组）
- OOD 凸包检测：近但凸包外的降级、共面降维、一维区间退化、可关闭回退
- 核心评价指标（相对误差、混合误差封顶、常数真值 R²）
- 空间场指标（质心误差、峰值误差、IoU、Dice）
- RBF 训练点恢复、预测值域 [0,1]、ROI 外置零、矩阵尺寸归一化、模型保存加载
- **质心对齐消融**（合成移动高斯场：对齐 vs 重影）
- POD-RBF 模态重构、解释方差、分量数截断
- OOD 检测分级与未拟合防护
- 结构化验证切分（整层留出覆盖全部工况、角落区域排除）
- 端到端合成数据集训练管线（含取消训练）
- 自定义配置贯穿坐标、ROI、评估平滑、误差阈值与模型包恢复
- 项目版本、Windows 发布包版本与许可证元数据一致性

GitHub Actions 在 Windows 与 Ubuntu（Python 3.11）上自动运行全部测试。

## 构建与发布

常规构建：

```powershell
.\scripts\build.bat
```

轻量版 Windows 发布构建：

```powershell
.\scripts\build_release.bat
```

轻量版不包含仿真训练数据和预训练 `.joblib` 模型文件，以减小下载体积。运行后请在 GUI 中选择本地兼容的 `data/` 目录。

## 当前限制与后续计划

- 瞄准优化的散布椭圆当前定义在目标法平面内（A1/A2 假设）；斜入射条件下地平面 → 法平面的投影变换尚未建模，REP/DEP 主轴与物理射程方向的绑定关系待确认后接入。
- OOD 检测为最近邻距离 + SVD 全局凸包 + 局部邻域凸包三层几何判定；F/M/P 三级阈值与自动邻居数已用真实结构化验证标定。局部凸包仍属于启发式支撑检查，数据网格改变后应重新运行校准；LOF/k-NN 密度比可作为后续补充。
- 训练矩阵读取与预处理结果缓存可进一步细化，支撑更大工况库。
- `gui/main_window.py` 仍承担较多 Tk 布局代码，后续可继续按控制器与视图组件拆分；核心指标提取、配置恢复与瞄准渲染已移出窗口类。
