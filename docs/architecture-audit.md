# Damage-GUI 双界面（桌面 + Web）技术架构审计

> 审计范围：`src/damage_gui`（35 个 Python 模块，约 6,700 行）、`scripts/`、`tests/`（147 用例）、`pyproject.toml`、CI。
> 目标：在**不复制预测/模型逻辑**的前提下，将现有 Tkinter 桌面应用演进为「共享科学计算核心 → 服务层 → 桌面/Web 双前端」的架构。
> 本报告只做分析与建议，不修改代码。

---

## 1. 现状架构图（Current Architecture Map）

```text
入口层    damage-gui (app:main → Tk GUI)     damage-gui-cli (cli:main)     scripts/*.py
                    │                              │                        │
界面层    gui/main_window.py (1719 行)            cli.py                     研究脚本
          gui/presentation.py  gui/widgets.py        │                        │
          gui/resources.py                            │                        │
                    │                              ┌──┴────────────────────────┘
任务层    tasks.py (TaskManager：线程 + 队列 + 状态机 + 协作取消) ◄── 仅 GUI 使用
                    │
服务层    model/bundle.py::DamageModelService（训练编排 + 评估）
          batch/runner.py::run_batch（批量执行器 + SQLite 追溯）
          model/registry.py（保存/加载校验）
                    │
算法层    model/rbf.py · pod.py · validation.py · ood.py · metadata.py
          data/loader.py · preprocessing.py
          evaluation/metrics.py · optimization/aim.py   ← 全部 UI 无关
                    │
支撑层    config.py · errors.py · logging_setup.py
          storage/db.py · repositories.py（SQLite 三表）
          visualization/plots.py（Matplotlib Figure 工厂）
```

关键量化事实：

| 维度 | 现状 |
|---|---|
| UI 无关代码占比 | 约 **85%**（gui/ 仅 1,828 行 / 6,679 行，且 gui/presentation、resources 半数逻辑可复用） |
| 业务逻辑泄漏进 GUI | `main_window.py` 中约 **300–400 行**属于可提取的服务层/校验/导出逻辑 |
| 反向依赖（下层→gui） | **2 处**：`storage/db.py`、`logging_setup.py` → `gui.resources.app_base_dir` |
| 隐性 UI 后端耦合 | **1 处**：`visualization/plots.py` 模块级 `matplotlib.use("TkAgg")` |
| CLI 已验证的"无 GUI 路径" | `cli.py` 证明 predict/batch/info 均可在无 Tk 环境运行 |

---

## 2. 依赖图与违规点（Dependency Map）

### 2.1 实际 import 依赖（箭头 = "依赖于"）

```text
gui/main_window ──► bundle/registry/batch/tasks/plots/storage/config/presentation/loader/metrics
cli             ──► batch/schema/runner · registry · loader · config · errors · logging_setup
model/bundle    ──► data/ · config · metrics · ood · pod · rbf · validation · metadata
batch/runner    ──► storage(仓库) · model/bundle · data · metrics · errors · config
storage/db      ──► gui/resources        ⚠ 违规：存储层依赖 GUI 包
logging_setup   ──► gui/resources        ⚠ 违规：基础设施工具依赖 GUI 包
visualization/plots ──► config(含 UI 配色) · data/preprocessing · TkAgg 后端 ⚠
tasks           ──► errors               ✓ 仅此一项，纯净
optimization/aim ──► numpy/scipy         ✓ 纯净（无 matplotlib，文档明确声明）
evaluation/metrics ──► numpy/pandas/config ✓ 纯净
app.py          ──► gui/main_window（模块级）⚠ Web 侧 import damage_gui.app 会连带拉起 Tk
```

### 2.2 四个关键违规/风险点

1. **`storage/db.py:13` 与 `logging_setup.py:13` 导入 `damage_gui.gui.resources.app_base_dir`**
   - 违反分层（存储层→GUI 包）。当前侥幸可用：`resources.py` 本身只 import `sys/pathlib`，不拉起 tkinter。
   - 但 Web 服务器部署到无 Tk 的 Linux 容器时，任何对 "storage 层不得依赖 gui 包" 的后续强化（如在 `gui/__init__.py` 加 Tk 检查）都会引爆。
2. **`visualization/plots.py:15` 模块级 `matplotlib.use("TkAgg")` + import 时执行 `configure_matplotlib_fonts()`（含 Windows 字体路径）**
   - 三个 `render_*` 函数本身返回纯 `Figure` 对象（好设计），但模块级后端绑定使 Web 服务器 import 该模块即要求 TkAgg/Tk 可用。
   - 服务器渲染 PNG 必须切 `Agg`；桌面保持 `TkAgg`。这是 Web 化的**第一阻塞点**。
3. **`app.py` 模块级 `from damage_gui.gui.main_window import main`**
   - `app.py` 同时承担向后兼容 re-export（旧 joblib 反序列化依赖，**不可删**）与桌面入口两个职责。Web 侧任何 `import damage_gui.app` 都会拉起 tkinter。
4. **`config.Config` 混装科学配置与 UI 主题**
   - 同一个 frozen dataclass 里既有 `rbf_kernel/ood_*`，也有 `ui_bg/ui_primary` 等 15 个 UI 配色字段和 `APP_TITLE`。
   - `ModelBundle.config` 会把 UI 配色一起序列化进模型包（`from_mapping` 忽略未知字段，所以拆分是向后安全的，但需要一次性清理）。

---

## 3. 十个核心问题的逐项回答

### Q1 哪些模块已经 UI 无关？

| 模块 | 状态 | 说明 |
|---|---|---|
| `model/rbf.py` `pod.py` `validation.py` `ood.py` `metadata.py` `bundle.py` `registry.py` | ✅ 完全 | 纯 numpy/scipy/joblib；`DamageModelService` 接口干净（`train_bundle`/`predict_matrix`），progress/cancel 均为回调注入 |
| `data/loader.py` `preprocessing.py` | ✅ 完全 | 注意 `read_damage_matrix` 硬编码 `encoding="gbk"` + tab 分隔——服务器数据上传管道需保留该解析 |
| `evaluation/metrics.py` | ✅ 完全 | `extract_core_metrics`/`metric_row` 可直接服务 Web |
| `optimization/aim.py` | ✅ 完全 | 814 行纯数学；`optimize_aim` 只吃 ndarray + 轴向量 |
| `batch/schema.py` `runner.py` | ✅ 完全 | `run_batch` 已参数化 `output_path/db_path/progress/cancel_check`，天然适配服务端 |
| `tasks.py` | ✅ 完全 | 线程 + queue + poll 模式不含任何 Tk 语义，Web 侧可直接复用（事件改投 SSE/WS 即可） |
| `storage/db.py` `repositories.py` | ⚠️ 逻辑纯净，但 import 违规（见 2.2-1） |
| `errors.py` | ✅ 完全 | 错误分类可直接映射 HTTP 状态码 |
| `cli.py` | ✅ 本身就是"无 GUI 消费者"的活证明 |

### Q2 哪些业务/科学逻辑耦合在 Tkinter 中？

`main_window.py` 中以下逻辑与 Tk 控件混在一起，属于必须提取的服务层职责：

| 位置 | 逻辑 | 行数（约） |
|---|---|---|
| `_current_condition()` (L934-948) | 工况解析 + 范围校验——与 `cli._validate_condition` **重复实现** | 15 |
| `_record_training_to_db()` (L1169-1190) | 训练结果→SQLite 追溯（JobRepository 调用 + 核心指标提取） | 22 |
| `_finish_training()` (L1192-1234) | 训练产物落盘（accuracy/condition CSV 写到 `app_base_dir()`）+ 指标提取 + 状态文案 | 43 |
| `on_predict()` (L1386-1515) | **最大耦合点**：预测 + OOD 报告 + 真值匹配（`find_record`/`read_damage_matrix`）+ 焦点区指标计算（`metric_row`）+ 建议文案生成，与 20+ 处 UI 更新交织 | 130 |
| `on_optimize_aim()` (L1589-1651) | 散布参数解析校验（CEP/REP/DEP/ρ/θ 合法性）+ `optimize_aim` 调用 | 63 |
| `on_export_csv()` (L1517-1543) | 预测矩阵→DataFrame→CSV——与 `cli._cmd_predict` 的 `--export` 分支**重复实现** | 27 |
| `on_run_batch()` (L1298-1353) | 批量编排（parse→run_batch→TaskManager 提交），业务骨架可复用 | 55 |
| `_update_advice_card()` (L1062-1083) | 精度达标判定 + 建议文案（决策规则，非纯展示） | 22 |

### Q3 哪些代码桌面与 Web 可直接共享？

- 全部 Q1 ✅ 模块：训练、预测、OOD、批量、瞄准优化、指标、存储、任务状态机。
- `gui/presentation.py` 的选项映射表（`MODEL_TYPE_CHOICES`/`VALIDATION_CHOICES`）本质是枚举字典，可平移到共享层供 Web 表单复用（`metric_display` 的配色逻辑桌面专用）。
- `TaskManager`：Web 的"提交任务→轮询/SSE 订阅进度→取消"与 GUI 的"submit→after 轮询→cancel"是同一种事件模型。

### Q4 哪些 GUI 专属函数目前住在 main_window.py？

纯 Tk 职责（保留在桌面端）：`_configure_styles`（约 190 行 ttk 主题）、`_build_layout/_build_header/_build_left_panel/_build_right_panel`（约 420 行）、`_make_card`、`_draw_figure`（FigureCanvasTkAgg 嵌入）、`_on_result_tab_changed`、`_set_animating/_animate_status_dot`、`_set_status/_set_progress/_set_busy`、`_update_*_card` 系列（UI 文案渲染）、`on_browse_*`（filedialog）、`_apply_window_icon`、`_handle_error`（messagebox）、`_on_close`。

### Q5 哪些绘图代码可复用？

- `render_heatmaps` / `render_full_prediction` / `render_aim_optimization` 均返回**后端无关的 `Figure`**，且接受 `config` 参数——设计良好。
- `find_crop_bounds` / `crop_matrix_and_extent` / `_style_heatmap_axis` / `_add_percent_colorbar` 可原样复用。
- 复用前提（必须改造）：①去掉模块级 `matplotlib.use("TkAgg")`，改为入口处按需选后端；②`configure_matplotlib_fonts()` 延迟到显式调用且幂等；③`_style_heatmap_axis` 引用 `CONFIG.ui_*` 配色——若拆分 Config 需同步处理（绘图配色与 UI 主题可合并为 `theme` 参数）。
- Web 渲染两种策略：**服务端 Agg 渲染 PNG**（复用现有函数，改动最小）或**下发降采样场数据由前端渲染**（交互更好，473×473 float32 ≈ 860 KB，可降采样或半精度传输）。

### Q6 哪些函数返回可序列化为 Web API 的 Python 对象？

| 现有产出 | 类型 | 序列化难度 |
|---|---|---|
| `ModelMetadata.to_dict()` | dict | ✅ 已就绪 |
| `BatchRowOutcome.to_output_dict()` | dict | ✅ 已就绪（含 round 处理） |
| `BatchReport` | dataclass（rows 已是 dict 化结构） | 🟡 加一个 `to_dict()` 即可 |
| `OODReport` | dataclass（纯 float/str/bool） | 🟡 加 `dataclasses.asdict` 包装 |
| `AimOptimizationResult` | dataclass：标量 + `value_field`/`kernel`（ndarray） | 🟡 标量直接序列化；场数据按 Q5 策略出图或降采样 |
| `predict_matrix` 返回值 | ndarray 473×473 | 🟡 服务端出 PNG / 客户端渲染 / 统计摘要（peak、area ratio 已有 `_row_summaries` 先例） |
| `accuracy_report`/`condition_report` | DataFrame | 🟡 `to_dict()`/`to_json()`；摘要用 `extract_core_metrics` |
| `ModelBundle` | joblib 二进制 | ⛔ 不走 JSON——服务端持有，API 只暴露 metadata |

### Q7 哪些部分需要 HTTP 适配器？

1. **文件选择语义**：`filedialog.askdirectory/askopenfilename/asksaveasfilename`（数据目录、模型、批量 CSV、导出目标）→ Web 需要"上传批量 CSV / 下载结果 CSV、PNG"+ 服务端固定 models 目录。
2. **路径策略**：`app_base_dir()`（db 路径、日志、报告 CSV、模型目录）→ 服务端需环境变量/配置注入的根目录（`DAMAGE_GUI_DB` 环境变量机制已存在，可扩展为 `DAMAGE_GUI_HOME`）。
3. **任务事件通道**：`TaskManager.poll()` 队列 → REST 轮询（`GET /jobs/{id}`）或 SSE/WebSocket；`TaskEvent` 快照结构几乎可直接作为 payload。
4. **进度/取消回调**：`ProgressCallback`/`cancel_check` 签名保持不变，Web 侧由 job 通道桥接——**无需改动核心**。
5. **校验重复**：GUI 与 CLI 两份工况校验 → 收敛为共享 `validate_condition()`，HTTP 层再包 422 响应。
6. **错误映射**：`DataValidationError→400/422`、`ModelLoadError→404/409`、`TaskStateError→409`、`OperationCancelled→任务终态`。

### Q8 同步 vs 长耗时操作

| 操作 | 耗时量级 | 现有执行方式 | Web 处置 |
|---|---|---|---|
| `predict_matrix` + OOD | 毫秒级 | GUI 主线程同步 | **同步 HTTP**（安全） |
| `optimize_aim` | 亚秒级（FFT 卷积 473²） | GUI 主线程同步 | **同步 HTTP**（可加超时保护） |
| 模型 load（joblib） | 秒级（含 OOD detector） | 同步 | 服务端启动时预加载 + 内存缓存 |
| 模型 save / 导出 CSV/PNG | 秒级 | 同步 | 同步或即发即弃 + 下载链接 |
| `train_bundle` | **分钟级**，有进度/取消 | TaskManager 后台线程 | **必须异步作业**（TaskManager 直接复用） |
| `run_batch` | 行数相关，**长耗时**，支持部分保留 | TaskManager 后台线程 | **必须异步作业** |

### Q9 Web v1 安全暴露的操作

- 模型信息/列表（`registry.load_model` + `metadata.summary_lines()`，只读）
- 单工况预测 + OOD 可信度（同步；含 peak/area 摘要，参照 `cli._cmd_predict` 输出）
- 瞄准优化（同步；结果摘要 + PNG）
- 小规模批量预测（v1 限制行数，如 ≤200 行，走异步作业 + 轮询）
- 历史与结果查询（`prediction_results`/`jobs` 只读 API——仓储层目前**只有写方法，缺读查询方法**，需补 `list_jobs/list_results`）
- 模型文件下载（服务端管理的注册目录）

### Q10 初期保持桌面专用的操作

- **训练**：输入是本地大目录（120 个 DamageMatrix 文件、gbk 编码私有数据），涉及数据上传管道、长任务与数据治理——v1 不上网。
- **数据目录浏览/扫描**：本地文件系统语义。
- **模型另存到任意本地路径**：Web 用服务端受管目录替代。
- **PyInstaller 打包交付**：纯桌面关注点（Web 依赖必须走 optional extras，避免进入 exe 体积）。

---

## 4. 耦合风险清单（Coupling Risks）

| # | 风险 | 影响 | 等级 |
|---|---|---|---|
| R1 | `plots.py` 模块级 `TkAgg` 后端绑定 + import 时字体配置 | Web 服务器（无 Tk 容器）import 即崩 | 🔴 阻塞 |
| R2 | `storage/db.py`、`logging_setup.py` → `gui.resources` 反向依赖 | 分层破坏；容器化/无头环境隐患 | 🔴 |
| R3 | `app.py` 模块级导入 GUI `main` + 兼容 re-export 混居 | Web 侧误 import 拉起 Tk；re-export 又不可删（旧 joblib 反序列化锚点） | 🔴 |
| R4 | `main_window.on_predict` 业务逻辑与 UI 更新 130 行交织 | 提取时回归风险最高的单点 | 🟠 |
| R5 | 工况校验、CSV 导出在 GUI/CLI 双份实现 | 行为漂移（GUI 报中文错误、CLI 报 DataValidationError） | 🟠 |
| R6 | `Config` 混装 UI 配色且随 `bundle.config` 序列化 | Web 侧配置语义混乱；`from_mapping` 忽略未知字段使拆分兼容但需测试覆盖 | 🟡 |
| R7 | `read_damage_matrix` 硬编码 gbk + tab 分隔 | 未来数据上传管道需保真该格式 | 🟡 |
| R8 | 仓储层缺读查询 API | Web 历史功能需新增方法（纯增量，风险低） | 🟡 |
| R9 | `DamageDataManager.scan_records()` 每次全目录扫描（`find_record` 内部也全扫） | 服务器高频预测时的性能损耗，需要缓存层 | 🟡 |

---

## 5. 目标包结构（Target Package Structure）

原则：**保持 `damage_gui` 顶层包名与现有 `damage_gui.model/batch/...` 导入路径不变**（旧 joblib 反序列化与 147 个测试都锚定这些路径），只做"新增 + 平移 + shim"。

```text
src/damage_gui/
├── core/                          # Phase 2 起：算法层聚合入口（可选，纯导出聚合）
│   └── __init__.py                #   from ..model, ..evaluation, ..optimization 聚合
├── services/                      # ★ 新增：应用/服务层（UI 与 HTTP 双向无关）
│   ├── __init__.py
│   ├── conditions.py              #   validate_condition()（GUI/CLI/Web 共用，收敛 R5）
│   ├── training_service.py        #   train_use_case：train_bundle + DB 追溯 + 报告产物落盘
│   ├── prediction_service.py      #   predict_use_case：预测 + OOD + 真值匹配 + 焦点指标 + 建议结论
│   ├── aim_service.py             #   散布参数校验 + optimize_aim + 结果摘要
│   ├── batch_service.py           #   包裹 run_batch（含输出路径策略）
│   ├── export_service.py          #   预测矩阵 CSV / Figure PNG 导出（GUI 与 Web 共用）
│   ├── history_service.py         #   jobs/prediction_results 只读查询
│   └── dtos.py                    #   OODReport/BatchReport/AimResult/核心指标 → JSON dict
├── runtime/                       # ★ 新增：路径与运行环境（从 gui/resources 平移）
│   ├── __init__.py                #   app_base_dir()/resource_path() 新家
│   └── logging.py                 #   （可选）logging_setup 迁入并指向 runtime
├── webapp/                        # ★ Phase 3 新增：Web 版
│   ├── __init__.py                #   create_app()（FastAPI 实例工厂）
│   ├── api/                       #   models.py / predict.py / aim.py / batch.py / jobs.py
│   ├── render.py                  #   Agg 后端 PNG 渲染适配（调 visualization.plots）
│   └── static/                    #   前端（或独立 frontend/ 仓库）
├── data/ model/ evaluation/ optimization/ batch/ storage/   # ← 原地不动（算法与数据层）
├── visualization/plots.py         # ← 改造：去模块级 TkAgg，字体配置惰性化（R1）
├── tasks.py                       # ← 原地不动（已被 GUI/服务层/Web 三方复用）
├── config.py                      # ← 改造：UI 配色迁至 gui/theme.py（R6）
├── gui/                           # ← 瘦身：main_window 只剩视图 + 事件绑定
│   ├── main_window.py             #   调 services/*，不再直接碰 repository/metric_row
│   ├── presentation.py  widgets.py
│   ├── theme.py                   #   ← ui_* 配色新家
│   └── resources.py               #   ← 变为 shim：from ..runtime import ...
├── cli.py                         # ← 改造：改调 services（与 GUI 同一用例层）
└── app.py                         # ← 改造：main() 内 lazy import 桌面 GUI（R3）
```

架构对齐目标概念：

```text
        data/ model/ evaluation/ optimization/   （科学计算核心，零改动）
                        ↓
        services/ + tasks.py + storage/          （服务/应用层）
                       / \
              gui/ (Tk)     webapp/ (HTTP)       （双前端适配）
```

---

## 6. 迁移阶段（Migration Phases）

### Phase 0 — 解阻塞（无行为变化，纯基础设施）
1. `visualization/plots.py`：删除模块级 `matplotlib.use("TkAgg")`；`configure_matplotlib_fonts()` 改为幂等函数，由 `gui/main_window.main()` 显式调用；`Figure` 工厂函数保持后端无关（服务器用 Agg，桌面由 TkAgg 注入 canvas）。
2. 新建 `runtime/`（平移 `app_base_dir/resource_path`），`gui/resources.py` 变 shim；`storage/db.py`、`logging_setup.py` 改 import `runtime`（消 R2）。
3. `app.py`：`from damage_gui.gui.main_window import main` 移入 `main()` 函数体内；re-export 原样保留（joblib 兼容）。
4. 验收：CI 全绿 + `python -c "import damage_gui.storage, damage_gui.visualization.plots"` 在无 Tk 环境可用。

### Phase 1 — 服务层提取（GUI 瘦身，桌面行为不变）
1. `services/conditions.py`：合并 GUI `_current_condition` 与 CLI `_validate_condition` 的校验。
2. `services/training_service.py`：吸收 `_record_training_to_db` + `_finish_training` 的落盘逻辑（报告 CSV 路径参数化）。
3. `services/prediction_service.py`：从 `on_predict` 提取预测/OOD/真值/指标/建议决策链，返回结构化结果对象（含 advice 文案键而非 Tk 标签更新）。
4. `services/aim_service.py`、`services/export_service.py`：同理提取散布参数校验与导出逻辑。
5. `main_window.py` 与 `cli.py` 改调 services；GUI 代码量预计从 1,719 行降至 ~1,100 行。
6. 验收：147 测试全绿 + GUI 手工回归（训练→预测→批量→瞄准→导出全链路）。

### Phase 2 — 序列化与 HTTP API（Web 后端可用）
1. `services/dtos.py`：为 OODReport/BatchReport/AimOptimizationResult/核心指标补 `to_dict()`。
2. `storage/repositories.py` 增只读查询（`list_jobs`、`list_prediction_results`，分页）。
3. `webapp/`：FastAPI——`GET /models`、`GET /models/{id}`、`POST /predict`、`POST /aim`、`POST /batch`（异步：复用 TaskManager，`GET /jobs/{id}` 轮询或 SSE）、`GET /jobs`。
4. `webapp/render.py`：Agg 渲染 PNG 端点（直接调 `render_heatmaps` 等）。
5. pyproject 增 `[project.optional-dependencies] web = ["fastapi", "uvicorn"]`——不进桌面依赖。
6. 验收：API 契约测试 + 桌面 CI 不受影响（web 为可选 extras）。

### Phase 3 — Web 前端与部署
- 前端（视口热图/表单/任务进度，参照既有设计稿）、模型注册目录、容器化（Dockerfile：`pip install .[web]`）、鉴权与审计。

### Phase 4 —（可选）服务端训练
- 数据上传管道（保留 gbk/tab 解析）、训练作业队列、OOD 阈值在线校准。**明确延后**：数据治理与长任务运维成本高，桌面训练已完备。

---

## 7. 预计变更文件清单（Specific Files Likely to Change）

| 文件 | 阶段 | 变更性质 |
|---|---|---|
| `src/damage_gui/visualization/plots.py` | P0 | 移除模块级后端绑定；字体配置惰性化（**不动渲染数学**） |
| `src/damage_gui/gui/resources.py` → `runtime/` | P0 | 平移 + shim |
| `src/damage_gui/storage/db.py`、`logging_setup.py` | P0 | 改 import 路径（各 1 行） |
| `src/damage_gui/app.py` | P0 | lazy import 桌面入口（re-export 不动） |
| `src/damage_gui/services/*.py` | P1 | 全新（从 main_window 提取） |
| `src/damage_gui/gui/main_window.py` | P1 | **大改**：删去业务逻辑段，改调 services |
| `src/damage_gui/cli.py` | P1 | 改调 services（`_validate_condition`/导出分支去重） |
| `src/damage_gui/config.py` + 新 `gui/theme.py` | P1 | UI 配色字段迁移（`from_mapping` 兼容旧模型包） |
| `src/damage_gui/storage/repositories.py` | P2 | 增只读查询方法（纯增量） |
| `src/damage_gui/webapp/**` | P2/P3 | 全新 |
| `pyproject.toml` | P2 | web extras + 可能的 console script `damage-gui-web` |
| `.github/workflows/test.yml` | P2 | 增 web extras 的 lint/test job |
| **不动** | — | `model/*`、`data/*`、`evaluation/*`、`optimization/*`、`batch/*`、`tasks.py`、`errors.py` 的公共 API |

---

## 8. 测试稳定性风险（Risks to Test Stability）

| # | 风险 | 缓解措施 |
|---|---|---|
| T1 | **数值回归黄金值**（`test_numerical_regression.py`，容差按双进程实测漂移=0 设定）对任何波及计算路径的重构零容忍 | P0–P1 只动 import/编排层，**严禁触碰** `rbf/pod/ood/metrics/aim/preprocessing` 的数值行为；每个 Phase 跑双平台 CI 确认 |
| T2 | **旧 joblib 反序列化锚点**：`damage_gui.app.*` 与 `damage_gui.model.*` 导入路径被 pickle 引用 | 模块只增不删；`app.py` re-export 与 `aim_optimization.py` 式 shim 模式延续到一切平移 |
| T3 | `test_cli.py` 对 CLI 输出文本的断言可能因改调 services 而变化 | Phase 1 保持 CLI 输出逐字符不变（services 返回结构，CLI 负责打印格式） |
| T4 | `test_storage.py` 依赖 `resolve_db_path` 行为（env 变量 > 显式路径 > app_base_dir） | `runtime.app_base_dir` 平移后语义必须完全一致；补一条"无 Tk 环境 import storage"的守卫测试 |
| T5 | `test_config_integration.py` 可能断言 `Config` 的 UI 字段 | 迁移配色时先查测试引用；`from_mapping` 忽略未知字段已保证旧模型包加载兼容 |
| T6 | Matplotlib 后端切换影响 Windows CI 的 GUI 相关测试/构建 | P0 后桌面入口显式 `matplotlib.use("TkAgg")` 再建窗口；CI 增无头导入冒烟测试 |
| T7 | PyInstaller 构建把新增 `services/webapp` 打进 exe | optional extras 不进 base 依赖；build spec 校验（CI build job 已有产物校验） |
| T8 | `TaskManager` 被 Web 复用时的并发语义（同 kind 互斥、队列积压） | 现有 `test_tasks.py` 覆盖状态机；Web 侧新增并发提交/取消的 API 级测试 |

---

## 9. 结论

这套代码库的分层质量**显著高于典型科研工具**：算法层零 UI 依赖、CLI 已验证无头路径、任务状态机与存储层天然 UI 无关、模型可追溯链完整。双界面化的真实工作量集中在三处：

1. **四个阻塞点**（TkAgg 模块级绑定、两处 storage→gui 反向依赖、app.py 入口耦合）——都是行级修复，Phase 0 一次清零；
2. **`main_window.py` 约 350 行业务逻辑的提取**——这是唯一需要细致回归验证的部分（尤其 `on_predict` 的 130 行交织代码）；
3. **序列化 DTO 与只读查询 API 的增量建设**——纯新增，无破坏面。

不需要复制任何预测/模型逻辑；`DamageModelService`、`run_batch`、`optimize_aim`、`TaskManager` 将原封不动地同时服务桌面与 Web。
