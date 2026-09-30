# DamageLab 桌面版使用指南（Qt）

Qt 桌面版（`damage-gui-qt`）是 DamageLab 的主桌面产品：CAE 风格工作台，
覆盖训练、预测、批量、验证、模型库与历史追溯全流程。旧 Tkinter 工作台
（pip 入口 `damage-gui`）保留为 legacy，不再演进，建议迁移到 Qt 版。

## Getting Started

### 从源码运行

```bash
python -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\Activate.ps1
pip install -e ".[desktop-qt]"
damage-gui-qt
```

### 从发布包运行

下载对应平台发布包（`DamageLab-<版本>-<平台>`）：

- **macOS**：`DamageLab.app` 拖入 `/Applications`（或任意可写目录）后双击。
  未签名构建首次启动需 **右键 → 打开** 确认一次。
- **Windows**：解压 onedir 目录，运行 `DamageLab.exe`。
  SmartScreen 提示时选择"更多信息 → 仍要运行"。
- **Linux**：解压后运行目录内 `DamageLab` 可执行文件
  （未实机验证；Wayland 下如遇问题用 `QT_QPA_PLATFORM=xcb ./DamageLab`）。

发布包不需要安装 Python 或任何依赖。数据（SQLite / 日志 / 报告）自动写入
用户数据目录，见下文"数据目录"。

## 基本工作流

### Load Model（加载模型）

预测页 → 菜单 File → Open Model（`Cmd/Ctrl+O`），选择 `*.joblib` 模型文件。
加载时自动校验：文件存在性、joblib 完整性、sidecar 元数据与内嵌元数据一致性。
旧版无元数据模型可加载（日志提示无追溯信息）；空 sidecar（写入中断）按缺失
处理，不阻断加载；损坏的 sidecar JSON 会给出明确错误。

### Prediction（预测）

右侧 Inspector 输入工况 `(h, v, deg)` 与毁伤等级 → Run Prediction（`F5`）。
深色科学视口显示预测场 / 真值场（有数据时）/ 误差场；工具栏支持：

- **Reset**：复位视图
- **Pan / Zoom**：平移、框选缩放
- **Probe**：鼠标取值（像素坐标 + 场值）
- **Export**：导出 PNG（300 DPI）

结果显示峰值强度、毁伤面积比、OOD 可信度分级与耗时。

### Batch（批量预测）

批量页 → Open Batch CSV 导入工况 CSV（列：`job_id,h,v,deg,level`）→ Validate
校验 → Run。行级失败隔离（单行出错不中断批次），输出 CSV 每行携带模型版本、
OOD 分级、真值对照指标与耗时；可选真值数据目录与输出路径。

### Validation（验证）

验证页选择结构化验证方式（Random / Leave-h-out / Leave-v-out / Leave-deg-out /
Corner Holdout）→ Run。结果含 Raw/Smoothed 双口径指标与空间指标，可导出
JSON 汇总。

### Training（训练）

训练页 → Open Dataset 选择本地数据目录（文件名
`DamageMatrix_<F|M|P>_h_<h>_v_<v>_deg_<deg>`）→ 选择模型类型（RBF / POD-RBF）、
验证方式与参数 → Run。训练在后台线程执行，可取消；完成后可直接注册到模型库。

### Model Registry（模型库）

模型库页列出已注册模型（model_id、等级、类型、版本、生命周期状态），支持：

- **Activate**：设为当前预测模型（DRAFT → VALIDATED → ACTIVE 生命周期）
- **Register**：注册当前训练产物（含验证证据）
- **相关任务 / 验证历史**：跳转历史页过滤查看
- 搜索 / 等级 / 状态筛选

### History（历史）

历史页追溯全部任务（训练 / 预测 / 批量 / 验证）：状态、耗时、输入参数、
结果摘要；双击任务可查看详情并回填预测输入。

## Keyboard Shortcuts

| 快捷键 | 功能 |
|---|---|
| `Cmd/Ctrl+O` | 打开模型 |
| `Cmd/Ctrl+S` | 保存模型 |
| `Cmd/Ctrl+R` | 运行当前页主操作（预测 / 批量 / 验证 / 训练） |
| `Cmd/Ctrl+F` | 聚焦当前页搜索框（模型库 / 历史 / 批量 / 验证） |
| `Cmd/Ctrl+E` | 导出当前视图（预测 PNG / 验证 JSON） |
| `Cmd/Ctrl+L` | 展开 / 收起日志面板 |
| `F5` | 运行预测 |
| `Cmd/Ctrl+Q` | 退出 |

macOS 上为 `Cmd`，Windows/Linux 为 `Ctrl`。

## 数据目录

桌面版（含发布包）所有运行时数据写入平台用户数据目录：

| 平台 | 目录 |
|---|---|
| macOS | `~/Library/Application Support/DamageLab` |
| Windows | `%APPDATA%\DamageLab` |
| Linux | `~/.local/share/DamageLab` |

包含：`damage_gui.db`（SQLite 追溯库）、`logs/damage_gui.log`（轮转日志）、
训练报告 CSV。环境变量 `DAMAGE_GUI_HOME` 可显式覆盖（便携式部署 / 测试隔离）。
源码模式运行时使用项目根目录（开发习惯不变）。

## 语言

右上角语言按钮即时切换中文 / English，覆盖菜单、工作区、图表标签与
导出文件名；不改变数据格式与科学结果。

## 打包（面向维护者）

```bash
pip install "pyinstaller>=6,<7"

# macOS / Linux
scripts/build_qt_release.sh             # PYTHON=.venv/bin/python 可指定解释器

# Windows
scripts\build_qt_release.bat
```

- spec：`scripts/damagelab-qt.spec`（Qt 入口、SVG 图标集、应用图标、
  Matplotlib 资源；排除 Tkinter / Web 后端与未用 Qt 模块）
- 产物：`release/DamageLab-<版本>-<平台>/`（macOS 含 `DamageLab.app`，
  由 PNG 经 `iconutil` 生成 .icns）
- 签名：无证书，**未签名本地构建**（macOS ad-hoc）
- 已知平台问题：
  - macOS 首次运行 Gatekeeper 需右键打开（未签名）
  - 全新用户首次启动多耗时数秒（Matplotlib 字体缓存一次性构建）
  - Linux 未实机验证（CI 覆盖 Ubuntu 单元测试）
