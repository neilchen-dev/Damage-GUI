# 架构深度审计（第二轮）— 进一步优化与轻量化机会

**日期**: 2026-10-20 · **基线**: 第一轮优化（去 Tk/pandas/sklearn）+ 修复已合入工作区 · **方法**: 依赖图梳理 + importtime 实测 + 调用方验证

---

## 一、实测数据

| 入口 | 导入耗时 | 驱动链 |
|---|---|---|
| `damage_gui.app` / `desktop` | 0.04s | ✅ 已惰性化（PEP 562） |
| `damage_gui.webapp` | 0.16s | ✅ fastapi 已函数内惰性 |
| `damage_gui.model.bundle` | 0.25s | scipy.interpolate/ndimage |
| `damage_gui.visualization.plots` | 0.35s | matplotlib |
| **`damage_gui.cli`** | **0.53s** | ❌ 顶层拉起全栈（`cli.py:18-25`） |

依赖体积（.venv）：**PySide6 1.2GB**、**scipy 99MB**、numpy 34MB、matplotlib 33MB。

## 二、架构问题（结构性，按优先级）

### A1. `cli.py` 未惰性化 —— `damage-gui-cli -h` 也要 0.53s

`cli.py:18-25` 顶层直接 import `model.registry`（joblib）→ `model.bundle`（numpy+scipy）→ `experiments.baselines`（scipy.interpolate，占 137ms）。对照：`app.py` 用 PEP 562 做到 0.04s。
**修复**：import 移入各子命令函数，或复用 `app.py` 的 `__getattr__` 表。预计 → <0.1s。工作量小。

### A2. `model.bundle` → `experiments.baselines` 反向依赖

核心训练链路（`model/bundle.py:21`）顶层依赖"研究脚本层"experiments（其 `__init__.py` 自述依赖 pandas）。方向颠倒：`baselines.py`（LinearInterpField/NearestNeighborField）应下沉到 `model/` 或独立层。当前靠 `experiments/__init__.py` 惰性隔离才没把 pandas 拉回来，属脆弱平衡。

### A3. `batch ↔ services` 双向耦合

`batch/schema.py:15` → `services.conditions`；`batch/runner.py:27` → `services.export_service`；同时 `services/batch_service.py:7-8` → `batch.*`。当前碰巧无环，但两个子包互为上下游。建议：`validate_condition` 下沉到 `data/` 或 `services` 内聚批量逻辑。

### A4. `batch/__init__.py` eager import 拉起全栈

`import damage_gui.batch` 即触发 runner → model.bundle → scipy 链。应改为 PEP 562 惰性（`services/__init__.py:26` 已有现成范式）。

### A5. 次要

- `model/metadata.py:20` 从包根 `damage_gui` 取 `__version__`——中层依赖包根初始化，应直接从 `config.VERSION` 取
- 根 `__init__.py` docstring 仍列 "gui Tkinter 主窗口与小部件"，未提 qt/webapp/runtime/storage/services/batch——包地图过时
- `qt` 内部 widgets↔workflow 靠函数内 import 解环（activity_panel.py:20 ↔ workflow.py:100），脆弱但可用

## 三、轻量化机会（依赖裁剪）

### B1. ⭐ experiments/ 的 pandas 残留 —— "去 pandas" 未真正完成

`experiments/{tracking,uncertainty,drift,benchmark,runner}.py` 5 个模块仍顶层 `import pandas`；`drift.py:42,49` 的 `pd.read_csv`/`pd.to_numeric` 与 `data/table.py` 功能直接重复。迁移后 pandas 可从所有 extras 中彻底消失（`data-science` 只剩 sklearn）。
**收益**：完成去 pandas 叙事；**风险**：experiments 是研究层，需数值回归测试护航（已有 test_experiments/test_benchmark）。

### B2. scipy 裁剪 —— 只建议"全或无"

99MB，是最大的可裁依赖。使用面审计结论：

| 可 numpy 替代（≤20 行） | 绑死 scipy |
|---|---|
| `ndimage.center_of_mass`（metrics/rbf/pod，3 处） | **`RBFInterpolator`（rbf.py:8、pod.py:21，核心算法）** |
| `ndimage.shift(order=1)`（双线性平移） | **`spatial.Delaunay`（ood.py 凸包判定，依赖 Qhull）** |
| `gaussian_filter` / `zoom(order=1)`（preprocessing） | |
| `fftconvolve` / `map_coordinates`（aim.py） | |
| `spearmanr` / `ks_2samp`（experiments） | |

**结论**：部分替代只省导入时间、不省体积，且引入数值语义漂移风险，**不推荐**。完全移除需自研 RBF 求解器（~50 行 numpy 线性系统，可行）+ Delaunay 替代（凸包含判定可用单形重心坐标法，但工程量大）。若"零 scipy 核心链路"是目标（serverless/嵌入式），值得单独立项；否则保留。

### B3. Qt 层 matplotlib 顶层 import（3 处）

`qt/widgets/field_view.py:10-11`、`qt/panels/training.py:7-8`、`visualization/scientific_theme.py:10-13` 在模块级拉起 matplotlib。改惰性可加快 Qt 冷启动。Web 层（`webapp/render.py:11-14`）已是函数内惰性，干净。

### B4. PySide6 打包验证

spec excludes 已覆盖 WebEngine/Qml/Quick/3D/Multimedia 等（`damagelab-qt.spec:60-110`），较全面。⚠️ 注意 QtMultimedia 排除后 ffmpeg DLL（libavcodec 27MB×2）可能仍被 PyInstaller hook 收集——下次 Windows 打包时验证产物中无 `avcodec/avformat` 残留。

## 四、死代码与清理

| 项 | 状态 | 建议 |
|---|---|---|
| `src/damage_gui/aim_optimization.py`（兼容 shim） | 唯一调用方是 `tests/test_aim_optimization.py:12` | 改测试 import 后删除 shim |
| `scripts/` 10 个 `capture_*` + `qt_release_acceptance.py` | 一次性验证据脚本，仅在历史 phase 文档引用 | 归档 `scripts/archive/`（同步删 pyproject:123-124 两条 lint 豁免） |
| `qt/theme.py:47` 与 `qt/icons.py:11` 各自硬编码 icons 目录 | 轻微重复 | `theme.py` 改为 import `ICON_DIR` |
| 注释掉的代码 / TODO / FIXME | 全 src/ 零命中 | ✅ 干净 |

## 五、结论与建议路线

**立即可做（低风险高收益）**：A1（cli 惰性化）、A4（batch 惰性化）、B3（Qt matplotlib 惰性化）、C 类清理（shim 删除 + 脚本归档）+ A5 文档修正。

**下一个迭代**：A2（baselines 下沉）+ A3（batch/services 解耦）+ B1（experiments 去 pandas）——三者一起做，正好完成"核心链路零研究层依赖、全仓零 pandas"的架构叙事。

**需单独立项评估**：B2 完全去 scipy（99MB，含 RBF/Delaunay 自研，有数值回归风险）。

整体评价：分层约束（"算法/存储层零 GUI 依赖"）已达成且无越层；剩余问题集中在**同层反向依赖**与**入口层惰性化不彻底**，均为局部修复，无架构级返工需求。
