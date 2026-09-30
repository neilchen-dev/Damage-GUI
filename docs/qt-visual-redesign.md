# Qt Phase 2 — CAE Workbench Redesign

`qt-redesign` 分支的 PySide6 前端在 Phase 1.x 的基础上整体重构为 CAE 桌面工作台形态。业务逻辑与 Phase 1 完全一致：PredictionService、模型 registry、OOD、TaskManager / TaskAdapter、SQLite 与 metadata 均未改动，仅重排 presentation layer。

## 结构

```
Application Bar (42px)   DamageLab · File/Model/Analysis/View 菜单 · 当前模型 · 语言
Tool Rail (56px)         图标导航：Prediction / Batch / Validation / Aim / History / Settings
Workspace                Page Header (44px) + 深色 Scientific Viewport + Viewport Toolbar
Inspector (280px)        INPUT / RESULT / MODEL 三个 section，divider 分隔，无卡片无 GroupBox
Activity Panel (34px)    Jobs / Results / Logs 标签条 + ● Ready 状态，点击展开 180–240px
```

- Tool Rail 不显示永久文字，tooltip 提示功能名；选中态为浅色背景 + 左侧 3px accent。
- 菜单接线：File（Open/Save Model、Quit）、Model（Model Details…）、Analysis（Run Prediction，F5）、View（Reset/Pan/Zoom/Probe/Export，与视口工具栏双向同步）。
- Workspace Header 单行显示 `Prediction` 与 `F / RBF / model-id`。

## 深色科学视口

- 视口表面 `#15191F`，工具栏条 `#1B2028`；应用 shell 保持浅色。
- Matplotlib figure 在渲染后统一重设 figure/axes 背景、tick、axis label、title、colorbar 为深色主题；数据、cmap 与科学结果不变。
- Viewport Toolbar：`Reset Pan Zoom Probe Export` 紧凑工具按钮；Probe 激活后在工具栏左侧实时读出光标处的 x / y / 毁伤强度。

## Inspector

- INPUT：Damage Level（只读，模型绑定单一等级）、Height / Velocity / Angle、Run Prediction。
- RESULT：Maximum、Damage Area、Confidence（● 着色）、Prediction Time。
- MODEL：Type、Level、Model ID（截断显示，tooltip 完整值）。

## Activity Panel

- 底部默认 34px 折叠条；点击任一标签或箭头展开，可拖动调节高度。
- 状态读数 `● Ready` 与状态消息着色复用 StatusBadge；日志进入 Logs 标签。

## Prediction 流程（不变）

Load Model → level / h / v / deg → PredictionService → damage field → OOD → result metrics。
切换模型清除上一模型结果；重复预测重置导航状态；导出当前 Figure。

## 运行

```sh
pip install -e '.[desktop-qt]'
damage-gui-qt
```

## 验证

```sh
python -m pytest tests/test_qt_workbench.py tests/test_phase1_services.py tests/test_tasks.py \
    tests/test_service.py tests/test_headless_imports.py tests/test_i18n.py -q
```

Qt 集成测试在独立 offscreen 子进程运行：合成数据训练真实模型，覆盖模型加载/保存、预测结果、深色主题（figure/axes 背景色断言）、Probe/Pan/Zoom 状态同步、中英文三种窗口尺寸、工具栏导航与 Inspector 切换、Activity 折叠展开、重新加载后结果清除。

本机 offscreen 截图位于 `outputs/qt_phase15/`、`outputs/qt_phase16/`、`outputs/qt_phase2/`，不纳入版本控制。截图使用合成模型，不代表真实模型精度。原生 macOS/Windows 交互与 Retina 实屏效果仍需在目标设备验收。

## Phase 1.7 — Design System & Desktop Finish

保留现有 Application Bar / Tool Rail / Workspace / Inspector / Activity 结构。
本阶段仅完善 Qt presentation：

- `qt/theme.py` 集中 shell、viewport、状态颜色及 spacing / typography / control height token；输入统一 34px，主按钮 36px。
- 空状态与 stack 明确使用深色背景，17px 标题、说明和紧凑加载按钮；Matplotlib 的轴、offset text、标题、grid 和 colorbar chrome 适配深色，不改数据或 colormap。
- `qt/icons/*.svg` 为统一 1.6px stroke 的自带 outline 集合；Rail 与 viewport 按钮按 hover / selected 动态着色，包含中英文 tooltip 与 accessible name。SVG 随 Python 包分发。
- ComboBox dropdown / SpinBox 使用同系列 chevron；统一 hover、focus、disabled 与 popup selection 样式。
- RESULT 行高 24px，状态使用着色圆点与文字；Model ID 固定宽字体、10 位摘要和完整 tooltip。
- Activity 默认实际占用 34px；点击标签展开，重复点击当前标签折叠，切换其他标签保留展开。展开默认 200px，可拖动至 180–220px。Splitter 同步分配高度，不留下折叠空白。

验证：29 项相关测试通过；Qt 测试新增空状态 palette、SVG 图标、输入高度、Activity 标签切换回归检查。中英文在 1440×900、1280×720、1100×700 下检查。实际 offscreen 截图位于 `outputs/qt_phase17/`（合成模型，非真实精度证据），已检查空状态、预测结果与 Activity 展开态。原生目标设备与 Retina 效果仍需实屏验收。

## Phase 1.8 — Loaded State & Scientific Result Polish

仅修改 Qt presentation、验收测试和截图脚本；保留 Shell 结构与共享 renderer，未修改 PredictionService / OOD / TaskManager / registry / SQLite / Web / CLI / Tkinter。

- No Model / Model Ready / Prediction Completed 三种状态完整覆盖。加载后隐藏 Load Model，显示轻量 Model ready 提示；header / Inspector 截断 ID、tooltip 显示完整值，Application Bar 的 tooltip 提供已有版本、创建时间和训练工况摘要。
- Qt 专用 i18n 统一图标题与 colorbar，语言切换直接更新当前图，不重新预测。figure / axes 均为 `#15191F`；ticks、labels、title、edge 使用集中科学主题 token；colorbar 保持原范围，使用五个百分比刻度。
- canvas 使用 Expanding；单图 compressed layout、有真值时只调整 Figure 内部为大预测图加两个辅助对照图。保留每张图的数组、extent、colormap、normalization 与 equal aspect。1440×900 fixture 主图宽约 554px；真值对照模式的预测图宽约 603px。
- 调用原服务的 Qt QThread worker 在后台计算，UI 显示 Predicting…、禁用输入和相关菜单 / toolbar、防止重复提交。保留上一张图；首次预测用轻量 running 提示。成功 / 失败后恢复控件；运行期间请求关闭会在计算完成后安全关闭。
- Confidence 使用真实 OOD level 与现有颜色；tooltip 显示距离、凸包及局部支撑信息。失败仅显示简短 Prediction failed，完整 traceback 进入 Activity Logs 与既有 logging 体系，保留上一张成功图与指标。
- Activity 默认折叠，Jobs 展示真实 Prediction SUCCESS 与 elapsed；无额外后端 job 模型。
- Export 仅有结果时启用，默认 300 DPI PNG 与 level / model / timestamp 文件名。
- 替换 Figure 时先清理旧图，再解除其 canvas 引用，并重置 toolbar history；Probe 读取新图且清理旧读数。连续 20 次真实预测后旧图 weakref 可回收、axes / widget 数量不增长。

验收：`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` → **237 passed**。覆盖 No Model、Loaded、Success、Error / retry、重复提交、20 次连续预测、Figure 回收、安全关闭、中文 / 英文、1440×900 / 1280×720 / 1100×700、实际 PNG DPI 和科学数组 / cmap / normalization 不变。Web 可选依赖按已有 pyproject 声明安装到本地 `.venv` 以运行完整测试，未修改其代码或依赖声明。

截图可重现：

```sh
QT_QPA_PLATFORM=offscreen .venv/bin/python scripts/capture_qt_loaded_states.py
```

`outputs/qt_phase18/` 包含规定四张截图、No Model / Model Loaded、中文与真值对照截图；`evidence.json` 记录实际工况、模型 ID、真实 OOD level / distance、指标与主图像素宽度。LOW 使用 h=2 / v=150 / deg=20（distance=0.5）；HIGH 使用训练工况 h=3 / v=100 / deg=10（distance=0）。截图来自 `tests/synthetic_data.py` 训练的 RBF 与保留原 detector 的 inference-only 模型包，不伪造 UI 指标或信心状态。该 fixture 的数值预测耗时可为 0ms（服务原有整数计时），UI 未人为放大。

原生 macOS / Windows 与 Retina 实屏交互仍需目标设备验收；offscreen 截图不等同于真实科学数据的精度验证。修改保留在工作区，未提交或推送。

## Phase 1.9 — Scientific Visualization Integration

本阶段保留全部 Qt shell 结构，只将 scientific visualization 融入 dark viewport。新增 headless-safe 共享主题、opt-in dark API、cividis-derived damage palette 与暗色零点的 cool/warm error palette，保留所有数值归一化、数组、坐标范围与默认前端渲染。优化 comparison 比例与贴近数据轴的窄 colorbar，并检查原生 Cocoa 2× Retina。详细实现、色图决策、截图、测试与 Tk 环境限制见 [Qt Scientific Visualization](qt-scientific-visualization.md)。
