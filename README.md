# 基于数据驱动的毁伤场快速预测系统

这是一个面向仿真毁伤数据的 Python 桌面工具：根据飞行/撞击工况重建二维毁伤场，并提供精度评估、可视化和瞄准点优化能力。

## 问题与目标

输入为工况参数 `(h, v, deg)` 与毁伤等级（`F`、`M`、`P`），输出为连续的 `473 × 473` 二维毁伤场，而非单一数值。

由于毁伤图案会随工况发生空间位移，直接逐像素插值容易产生图案淡化或重影。本项目将图案形状与空间平移分离后分别建模，以提升场重建质量。

## 方法流程

```text
仿真 DamageMatrix 数据
        → 双边滤波降噪
        → 质心提取与对齐
        → 在 (h, v, deg) 空间进行 RBF 插值
        → 质心恢复
        → 二维毁伤场预测
        → 指标评估、可视化与瞄准优化
```

- 使用双边滤波降低蒙特卡洛噪声，并尽量保留毁伤峰值和边缘。
- 使用质心对齐，将图案的形状变化与平移变化解耦，减少插值重影。
- 使用 RBF 插值在低维工况空间中重建高维二维场。
- 提供 RMSE、MAE、R²、毁伤面积比、相对误差和混合误差等指标。
- 支持基于 CEP 或 REP/DEP 概率散布模型的瞄准点优化。

## 项目结构

```text
.
├── src/damage_gui/
│   ├── app.py                 # GUI、数据读取、RBF 模型与精度评估
│   └── aim_optimization.py    # 独立的瞄准点优化数学模块
├── scripts/
│   ├── build.bat              # 常规 PyInstaller 构建脚本
│   ├── build_release.bat      # 轻量版 Windows 发布构建脚本
│   └── generate_results.py    # 从本地数据复现示例结果
├── tests/                     # 可重复运行的数值与指标测试
├── examples/                  # GUI 截图与真实示例结果
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

启动后，在 GUI 中选择本地数据目录、毁伤等级，训练或加载模型后即可输入工况进行预测。

## 图形界面

GUI 支持数据目录选择、模型训练/加载、工况输入、毁伤场可视化、CSV/PNG 导出以及瞄准点优化。

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

## 测试

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

测试覆盖了散布参数转换、概率核归一化、零散布极限行为和核心评价指标。

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

当前采用随机留出验证，适合检查插值精度，但对规则工况网格的未知条件预测可能偏乐观。后续将增加按高度、速度、角度整层留出或区域留出的结构化验证。

当前训练运行在 GUI 进程中；后续将通过后台线程进一步提升大数据量场景下的界面响应性。
