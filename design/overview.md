# DamageLab — CAE 工作台 UI 原型

**文件**: `design/damagelab-ui.html`（单文件，无外部依赖，浏览器直接打开）

## 布局结构（桌面优先）
| 区域 | 尺寸 | 说明 |
|---|---|---|
| 菜单栏 | 26 px | File / Edit / View / Model / Analysis / Results / Help + 版本号 |
| 工具栏 | 36 px | New / Open / Save / Run(F5) / Stop / Contours / Grid / Probe / SI units |
| 左侧项目树 | 200 px | PROJECT → Dataset / Model / Validation；ANALYSIS → Prediction / Batch Prediction / Aim Optimization；RESULTS → History / Export |
| 上下文属性面板 | 260 px | 随导航选择切换，一次只显示一组控件 |
| 中央可视化视口 | 弹性（主导区域） | Canvas 科学可视化 + 视口工具条 |
| 右侧结果面板 | 240 px | RESULT / VALIDATION / CONFIDENCE / Run info |
| 状态栏 | 24 px | 状态 + 网格信息 + 探针坐标读数 + 内存 + 时钟 |

## 上下文面板内容
- **Prediction**: h / v / θ 输入 + Run Prediction（主按钮，F5 快捷键）
- **Model**: 模型类型 / 损伤等级 / 验证方法 / POD 分量数 + Train / Load / Save
- **Aim Optimization**: 散布模型 / CEP / ρ / θ + Optimize + 最优解读出块
- 其余：Dataset（摘要+预览表）、Validation、Batch（含进度条）、History（可点击重载）、Export（格式复选+路径）

## 科学可视化
- 损伤场热图：种子化高斯叠加场，Viridis / Inferno / Cividis 色图
- Marching Squares 等值线（0.1–0.9，0.5 加深）
- 坐标轴 / 网格 / 色标（含刻度）
- 探针：鼠标十字线 + 状态栏实时 `x / y / D` 读数
- 视口联动：Dataset → 散点图，Validation → 预测-实测残差图（含 R² 标注与恒等线）

## 视觉规范
- 白 / 浅灰表面，1px 边框，3 px 圆角控件，无阴影、无渐变
- 蓝色 (#1f5fa8) 仅用于选中态与主操作；绿 / 琥珀 / 红仅用于状态
- UI 12–13 px，节标签 11 px 半Bold大写，页面标题 15 px
- 等宽字体用于全部数值、坐标、时间戳、ID（tabular-nums）
