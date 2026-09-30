# Phase 1.9 — Scientific Visualization Integration

本阶段保留 Qt Application Bar / Tool Rail / Workspace / Inspector / Activity 架构。仅修改绘图主题、FieldView 集成与对应验证；服务、模型、OOD、训练数据、数据库和任务逻辑均未修改。

## 实现文件

- `src/damage_gui/visualization/theme.py`：纯 Python `ScientificTheme` token，Qt 与 Matplotlib 共用，无 PySide6、backend 或 rcParams 副作用。
- `src/damage_gui/visualization/scientific_theme.py`：`apply_scientific_theme()`、当前图 i18n、viewport 专用色图、comparison 排布和随 equal-aspect 轴定位的 colorbar。
- `src/damage_gui/visualization/plots.py`：增加可选 keyword 参数 `theme="dark"` / `language="zh"|"en"`；原有默认调用与其绘图行为保持不变。
- `src/damage_gui/qt/widgets/field_view.py`：使用共享 helper，移除原来重复的背景 / ticks / colorbar / comparison 样式实现；替换 Figure 时匹配 Qt canvas 的 device pixel ratio。
- `src/damage_gui/qt/theme.py`：复用共享科学颜色 token，未调整 shell 结构。

## 颜色决策与数据保证

数值语义仍为 `0 = no / minimal damage`，`1 = maximum damage`。

现有全局 `DAMAGE_CMAP="YlGnBu"` 与 `ERROR_CMAP="RdBu_r"` 保持原样，既有 Tkinter / CLI / Web 和历史验证图片仍使用默认 renderer。浅黄纸张矩形来自 YlGnBu 的低端映射，改 axes 背景无法消除这一区域。因此只在 opt-in dark viewport 使用以下显示方案：

- Damage：`damage_dark_cividis`。采用 cividis 的蓝黄顺序梯度，在色表的最低 8% 区间连续融合至 viewport 背景；零值 RGBA 与 `#15191F` 完全一致。这里改变 RGB lookup table，不改变 Normalize，也不 threshold / mask / alpha 隐藏有限值。高低强度仍使用同一个 0–1 标尺，Probe 读数不变。
- Error：`error_dark_coolwarm`。负值为 cool blue、零为 viewport 暗中性色、正值为 warm coral。保留 `Prediction − Truth` 数据和已有 `[-err_limit, +err_limit]`，其中 `err_limit=max(max(abs(cropped_error)), 0.10)`，没有单边、独立或非线性的数值归一化。
- Prediction / Truth：完整共享 damage palette、vmin=0 / vmax=1、crop bounds 与坐标范围。不会各自按峰值重新缩放。
- OOD：HIGH / LOW 只使用现有 Inspector 状态。绘图函数没有读取 confidence 的接口，同一 magnitude 不会因为 confidence 改变颜色。

选择依据：viridis / cividis / magma / inferno 都属于顺序色图；turbo 的亮度方向会反转。cividis 的暗蓝低端更接近视口，不依赖红绿区分，其基础设计考虑了色觉缺陷与亮度线性。选用蓝黄而非暖色强度梯度，也让 field magnitude 与红色 LOW 状态保持清晰的视觉区分。参考 [Matplotlib 色图选择说明](https://matplotlib.org/stable/users/explain/colors/colormaps.html) 与 [cividis 原始研究](https://arxiv.org/abs/1712.01662)。

`outputs/qt_phase19/palette_review.png` / `.json` 对比 YlGnBu、viridis、cividis、magma、inferno、turbo 与本次显示色表。在 256 个采样点的线性 RGB 相对亮度检查中，新 damage palette 为单调递增；turbo 有 129 次亮度下降。低端融合后的色表是派生版本，不声称拥有未经测量的完整感知均匀性或独立色盲认证。旧证据色图不会被替换。默认导出 dark screen theme；本阶段没有新增 publication theme。

## 排布与 colorbar

- Figure / axes / PNG export 同为共享 viewport background。spines 使用低对比细线，默认无强网格。单图 title 为约 12 logical px 的 muted 标题，不重复 Inspector 指标。
- Prediction 主图在左，Ground Truth / Error 在右侧两行。仅更改 Figure 内部排布；图片保持 equal aspect，数据坐标比例不拉伸。
- 1440×900 offscreen：single 主图约 531 logical px，comparison 主图约 494px、Truth 约 286px。未盲目扩大主图；Truth 从之前辅助缩略图提升为可实际比较的科学场。
- colorbar 均为约 7.5 logical px 宽、距离轴约 8px，使用 parent axis 实际绘图区的 locator。轴因等比例而居中或留空时，colorbar 仍跟随真实数据框，高度与对应图完全一致。
- ticks 仅五个；Damage 为 0/25/50/75/100%，Error 保留以零为中心的带符号百分比。tick / label 字体克制，无外框；300 DPI export 使用相同色表、范围与背景。
- 布局设置与 locator 幂等，不添加 resize callback，不在刷新时创建额外 axes / colorbar。

## 验证

运行：

```sh
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
```

结果：**242 passed, 1 skipped（31.67s）**。原有 237 项测试全部通过；新覆盖包括：

- 默认 renderer 仍使用 YlGnBu / RdBu_r；输入矩阵、cropped arrays、extent、Normalize 对象和 clim 在 dark apply 前后保持不变。
- Prediction / Truth 同色表 / 同范围；Error 对称范围、暗色零点；damage 亮度不会反转。
- Chinese / English、1100×700 / 1280×720 / 1440×900 / 1600×1000。
- 1× / 2× Qt offscreen：canvas 实际像素数为 logical size × device_pixel_ratio，Figure DPI 不重复倍增；axes 和 colorbar 几何比例保持正确。
- 单图 20 次、comparison 20 次真实预测（各在 1× / 2× 下运行）；旧 Figure weakref 可回收、axes / widgets 数量稳定；另有 headless repeated comparison render 20 次。
- 300 DPI PNG 真实导出、背景像素、labels 不越界、colorbar 不漂移。
- 阻止 PySide6 / Qt / tkinter 导入的独立子进程仍可 dark render、CLI / Web import。

Tkinter import 测试唯一跳过：本地 Homebrew Python 3.14 有 tkinter Python 文件，但没有 `_tkinter` 二进制扩展。没有修改或删除 Tkinter；共享 renderer 的默认兼容行为已验证，但无法在该解释器中宣称完成 Tk GUI 运行验证。

原生 macOS 测试：

```sh
QT_QPA_PLATFORM=cocoa .venv/bin/python scripts/capture_qt_loaded_states.py --output outputs/qt_phase19_retina
```

原生 Cocoa 已完成真实合成模型预测与图像导出，**device_pixel_ratio=2**，canvas DPI=200、PNG export=300；抓图与 buffer size 的比例断言通过，截图已检查。macOS 对超出当前屏幕可用高度的窗口进行限制，因此 native 文件名标记的是请求尺寸；`evidence.json` 的每张 capture 记录实际 logical window 与 image pixel dimensions。例如请求 1440×900 的 native 图实际约 1440×831–832，抓图约 2880×1662–1664；1280×720 抓图为 2560×1440。四种指定尺寸的精确布局验收由 offscreen 测试覆盖，不以屏幕受限的 native 窗口冒充精确尺寸。

## 截图与重现

```sh
QT_QPA_PLATFORM=offscreen .venv/bin/python scripts/capture_qt_loaded_states.py
```

路径：`outputs/qt_phase19/`；Retina native：`outputs/qt_phase19_retina/`。

要求截图全部来自 `tests/synthetic_data.py` 训练的真实 RBF（未 mock UI 数据）：

- `1440x900_high_confidence.png`
- `1440x900_low_confidence.png`
- `1440x900_comparison_en.png` / `1440x900_comparison_zh.png`
- `1280x720_loaded_prediction.png` / `1280x720_loaded_prediction_zh.png`
- `1440x900_loaded_prediction.png` / `1440x900_low_confidence_zh.png`
- 额外 `1100x700_comparison_en.png` / `1280x720_comparison_en.png` / `1600x1000_comparison_en.png`
- `1440x900_comparison_export.png`：实际 300 DPI dark PNG。

`evidence.json` 记录真实工况、model_id、OOD distance / level、metrics、logical plot width、platform / DPI 及每张截图的真实尺寸。LOW 工况 h=2 / v=150 / deg=20，distance=0.5；HIGH 为训练工况 h=3 / v=100 / deg=10，distance=0。Inference-only export 保留原 trained model / detector / metadata，只不附带训练文件；comparison 则使用同一训练 fixture 的真值数据。没有为截图伪造 confidence、数值或模型。

修改保留在 `qt-redesign` 工作区，未提交或推送。
