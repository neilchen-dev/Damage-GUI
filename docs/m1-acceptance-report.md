# M1 验收报告 — 模型元数据 / SQLite 追溯 / 任务状态机 / 批量预测

日期：2026-08-23 ｜ 版本：2.1.0（自 2.0.0 升级） ｜ 范围：仅 M1（P0），未包含 M2/P2

---

## 1. Diff 概览

**修改（6 个文件，+309 / -103 行）**

| 文件 | 改动 |
|---|---|
| `src/damage_gui/model/bundle.py` | `TrainingCancelled` 挂入统一错误体系（`OperationCancelled` 子类）；`ModelBundle` 新增可选字段 `metadata`；训练完成自动构建元数据 |
| `src/damage_gui/gui/main_window.py` | 训练改走 `TaskManager`（不再直接持有线程/队列）；新增批量预测卡片；保存/加载走 registry；模型信息卡显示元数据；错误弹窗去 traceback（完整堆栈进日志）；`WM_DELETE_WINDOW` 安全关闭 |
| `src/damage_gui/config.py` | 新增 `CONDITION_LIMITS`（GUI 与批量 CSV 校验共用）；`VERSION` → 2.1.0 |
| `pyproject.toml`、`scripts/build_release.bat` | 版本同步 2.1.0（`test_project_metadata` 一致性测试通过） |
| `.gitignore` | 新增 `logs/`、`*.db`、`*.db-wal`、`*.db-shm` |

**新增（15 个文件）**

| 文件 | 职责 |
|---|---|
| `src/damage_gui/errors.py` | `DamageGuiError` 基类 + DataValidation / ModelLoad / Prediction / OperationCancelled / TaskState 五类错误 |
| `src/damage_gui/logging_setup.py` | 控制台 + `logs/damage_gui.log` 轮转文件（1MB×5），幂等初始化 |
| `src/damage_gui/model/metadata.py` | `ModelMetadata`（三版本号）、训练数据指纹、git SHA 采集、验证指标摘要 |
| `src/damage_gui/model/registry.py` | `save_model`（joblib + `*.meta.json` sidecar 双写）、`load_model`（分级校验） |
| `src/damage_gui/storage/db.py` | 路径解析（`DAMAGE_GUI_DB` 环境变量 → 应用根目录）、WAL 短连接、幂等 schema |
| `src/damage_gui/storage/repositories.py` | Model / Job / PredictionResult 三仓储，故障显式记录 |
| `src/damage_gui/tasks.py` | 任务状态机 + `TaskManager`（互斥、协作式取消、事件队列、shutdown） |
| `src/damage_gui/batch/{__init__,schema,runner}.py` | CSV 解析校验 / 批量执行器 |
| `scripts/batch_predict.py` | 批量预测 CLI 入口 |
| `tests/`（6 个新文件） | 见第 8 节 |

**未改动**：rbf / pod / ood / validation / metrics / aim / plots / loader / preprocessing / presentation / widgets / resources / 全部现有测试 / `app.py`（re-export 兼容层保持原样）。

---

## 2. 数据模型

### 2.1 SQLite（三表，`CREATE TABLE IF NOT EXISTS`，全部幂等）

```text
models                模型注册表（训练产物的元数据镜像）
  id TEXT PK          = ModelMetadata.model_id
  created_at / app_version / model_type / damage_level
  training_samples / training_data_hash / code_commit
  parameters_json / validation_json / artifact_path

jobs                  任务记录（kind: 'training' | 'batch_prediction'）
  id TEXT PK, kind, status(PENDING/RUNNING/SUCCESS/FAILED/CANCELLED)
  model_id → models.id (FK), input_source
  created_at / started_at / finished_at / duration_ms
  error_summary / details_json

prediction_results    批量预测逐行结果
  id INTEGER PK, job_id → jobs.id (FK)
  row_job_id / level / h / v / deg / status
  ood_level / ood_distance / peak_intensity / damage_area_ratio
  mean_relative_error / p95_hybrid_error
  duration_ms / error_summary / output_path / created_at
```

索引：`jobs(kind,status)`、`jobs(created_at)`、`prediction_results(job_id)`、`models(damage_level)`。

约束遵循：473×473 场阵**不入库**（仅摘要指标）；每次操作独立短连接 + WAL，无跨线程共享连接；不存储重型数组。对提示词建议的 5 表做了一处合并——本项目"验证"内嵌于训练流程（train_bundle 同时产出验证报告），不存在独立验证任务，故 `training_runs / validation_runs / prediction_jobs` 合并为 `jobs(kind)` 单表，信息不减、无冗余行。

**设计取舍说明**：`jobs.model_id` 保留外键（批量预测入库前先 upsert 模型，保证追溯链完整：models ← jobs ← prediction_results）。批量预测时若模型元数据缺失（旧版模型），`model_id` 为 NULL，外键可空，任务仍可追溯自身。

### 2.2 模型元数据（`*.meta.json` sidecar + joblib 内嵌双写）

示例（`build_metadata` 产出）：

```json
{
  "model_id": "9b74458d…(uuid4 hex)",
  "created_at": "2026-08-23T03:46:11+00:00",
  "app_version": "2.1.0",
  "schema_version": 1,
  "model_format_version": 1,
  "model_type": "rbf",
  "damage_level": "F",
  "training_samples": 9,
  "training_data_hash": "sha256:…（排序后「工况|源文件内容SHA256」列表的 SHA256）",
  "code_commit": "3866a1e",
  "parameters": {"validation_mode": "random", "rbf_kernel": "thin_plate_spline",
                  "rbf_smoothing": 0.0, "align_patterns": true, "…": "…"},
  "validation": {"method": "random", "train_time_seconds": 0.612,
                  "mean_relative_error": 0.374427, "p95_hybrid_error": "…", "r2": "…"}
}
```

**training_data_hash 同时覆盖工况组合与文件内容**：文件名相同但数据被替换时指纹变化（有单测验证）。

---

## 3. 元数据兼容策略（三版本号）

| 版本号 | 含义 | 演化规则 |
|---|---|---|
| `app_version` | 软件版本（`damage_gui.__version__`） | 随发版迭代；加载时仅展示，不阻断 |
| `schema_version` | `*.meta.json` 结构版本（当前 1） | **向后兼容读取**；高于当前 → `ModelLoadError`「请升级软件」；缺失字段 → `ModelLoadError`「sidecar 可能已损坏」 |
| `model_format_version` | joblib 模型包（ModelBundle 类布局）格式版本（当前 1） | 无元数据的旧包视为 0；反序列化失败统一转 `ModelLoadError`（不再裸抛 pickle 错误） |

加载分级（`registry.load_model`，全部有单测覆盖）：

| 情形 | 行为 |
|---|---|
| 文件不存在 / 非 joblib / 非 ModelBundle | `ModelLoadError`（明确中文信息） |
| sidecar 损坏（非法 JSON）/ 缺字段 / schema 过高 | `ModelLoadError` |
| sidecar 与内嵌 model_id 不一致 | `ModelLoadError`（防模型与元数据错配） |
| **旧版模型**（无 sidecar、无 metadata 字段） | **正常加载**，日志 WARNING「无追溯信息」，GUI 状态栏与模型信息卡提示「旧版模型」 |
| 仅有内嵌 metadata（sidecar 被删） | 使用内嵌元数据，正常加载 |

向后兼容红线：`ModelBundle` 新字段带默认值，旧 pickle 可反序列化；`app.py` re-export 层未动，旧模型按 `damage_gui.app.*` 路径反序列化不受影响；`TrainingCancelled` 异常名不变（现为 `OperationCancelled` 子类），既有 `isinstance` 捕获继续生效。

---

## 4. SQLite 故障降级验证（不静默）

策略：仓储层所有操作捕获 `sqlite3.Error` → `logger.exception` 记录 **ERROR 级完整 traceback**（含操作名与库名）→ 返回 `None/False` 让调用方感知。计算主流程（训练、预测、批量）**照常完成**，但追溯失败显式可见：

| 验证点（单测断言） | 结果 |
|---|---|
| 坏库路径下 `upsert_model` / `insert_job` / `get_job` / `record_training_run` / `record_batch_results` 返回 False/None | ✅ `RepositoryFailureTests`（4 用例） |
| 每次失败都有 `assertLogs("damage_gui.storage", level="ERROR")` 命中 | ✅ 同上 |
| 批量预测在坏库下：结果 CSV 照常落盘、`success_count` 不受影响、`db_recorded=False` | ✅ `test_db_failure_degrades_explicitly` |
| GUI / CLI 侧：`db_recorded=False` → 状态栏/ stderr 追加「警告：结果未写入 SQLite 追溯数据库，详见日志」 | ✅（GUI 状态拼接 + 脚本冒烟输出可见） |

不做的事：不重试、不弹模态框打断用户——降级原则是"计算可继续，追溯失败必须留痕（ERROR 日志 + 界面警告 + 返回值标志）"。

---

## 5. 任务状态机验证

```text
PENDING → RUNNING → SUCCESS | FAILED
PENDING → CANCELLED（启动前取消）
RUNNING → CANCELLED（协作式：worker 检查 cancel_check 后抛 OperationCancelled，
           或在取消请求后正常返回——此时保留部分结果）
终态（SUCCESS/FAILED/CANCELLED）不接受任何转移 → TaskStateError
```

| 验证点 | 结果 |
|---|---|
| 合法路径 PENDING→RUNNING→SUCCESS 记录 started_at / finished_at / duration_ms | ✅ |
| 终态再转移、PENDING→SUCCESS 跳步、RUNNING→PENDING 回退均抛 `TaskStateError` | ✅ |
| 同 kind 重复提交被拒（`submit` 抛 `TaskStateError`） | ✅ |
| worker 抛异常 → FAILED + error_summary + `logger.exception` | ✅ |
| worker 抛 `OperationCancelled` → CANCELLED；取消后正常返回 → CANCELLED 且 result 保留（批量部分结果语义） | ✅ |
| 事件流 started/progress/finished 经队列投递，GUI 主线程 `poll()` 消费 | ✅ |
| `shutdown(timeout)` 请求取消并限时 join，关窗不悬挂 | ✅ |

GUI 解耦达成：`main_window.py` 不再 import `threading`/`queue`，不持有线程对象；训练与批量统一 `task_manager.submit(kind, work)`，`_poll_tasks()` 以 80ms `root.after` 派发到主线程。

---

## 6. Batch 验收

**输入**（`job_id,h,v,deg,level`；job_id/level 可选，`dtype=str` 保留前导零）→ 校验 → 预测 → 输出。

- 文件级错误（缺列 / 文件不存在 / 无数据行）→ `DataValidationError` 整批拒绝；
- 行级错误（非数字 / 超工况范围 / level 非法）→ 该行 FAILED，**不中断批次**；
- level 与模型等级不一致 → 该行 FAILED（`PredictionError`）；
- 命中精确工况 → 自动加载真值计算 MeanRE / P95（未命中则留空）；
- 每行输出：输入回显、status、model_id / model_version、OOD 分级与距离、峰值强度、毁伤面积占比、真值对照指标、耗时、错误信息；
- 取消：剩余行不再处理，`cancelled=True`，已完成行保留在输出；
- 追溯：模型 upsert → jobs（SUCCESS/CANCELLED）→ prediction_results 单事务写入。

**端到端冒烟**（`scripts/batch_predict.py`，4 行输入含 1 行超范围 + 1 行等级不符）：

```text
批量预测完成: 成功 2/4，失败 2，耗时 41 ms        exit=1（有失败行）
SQLite: jobs=[('batch_prediction','SUCCESS')]  models=1  results=4
hit 行 mean_relative_error=0.374（命中真值）, ood_level=high；miss 行无真值指标
```

退出码约定：全部成功 `0`；存在失败行或取消 `1`；输入不可用 `2`。

---

## 7. GUI 回归

- 现有 83 个用例全部通过（算法/评估/OOD/优化/管线行为零回归）；
- GUI 实例化冒烟（Windows）：批量卡片控件存在且初始态正确（运行=normal，取消=disabled）、`TaskManager` 就绪、`CONDITION_LIMITS` 与原值一致、`_on_close()` 正常销毁窗口；
- 交互行为对齐原版：训练进度条/阶段文案、取消训练、训练完成自动导出两份 CSV 报告、模型保存/加载对话框、预测/瞄准优化主线程路径——均保持原语义，仅底座从手工线程换成 TaskManager；
- 错误弹窗变化：不再展示 traceback，改为「详细信息已记录到日志文件 logs/damage_gui.log」；完整堆栈进轮转日志；
- PyInstaller 打包路径未改动（`build.bat` / `build_release.bat` 逻辑不变，仅版本号字符串），`test_project_metadata` 三处版本一致性通过。

---

## 8. 测试结果

```text
$ python -m unittest discover -s tests
Ran 135 tests in 3.651s    OK
```

新增 52 个用例：`test_errors_logging`（4）、`test_metadata`（10：三版本号/指纹稳定性与内容敏感性/roundtrip/schema 过高拒绝/缺字段拒绝/sidecar 双写/roundtrip 加载/损坏文件/错误类型/文件不存在/model_id 篡改/旧版模型）、`test_storage`（11：schema 幂等/坏路径 ERROR 日志/环境变量覆盖/models upsert+jobs CRUD/组合写入/批量结果/4 个故障降级）、`test_tasks`（9：转移表×3/成功流+进度/重复提交/异常 FAILED/OperationCancelled/协作取消/shutdown/空取消）、`test_batch`（10：解析×6/执行器×4）。

测试风格沿用仓库既有 unittest + 临时目录 + `sys.path` 注入约定，未引入新测试依赖。

---

## 9. 已知限制与后续（M2/P2 范围）

1. **GUI 批量卡片暂不显示历史任务列表**——jobs 数据已入库，查询界面留给后续（M2+）。
2. **CLI 仅有批量入口**（`scripts/batch_predict.py`）；`train/predict/info` 子命令属 P2 最小 CLI，未在本轮实现。
3. **CI 未升级**——ruff / 数值回归 / Windows 构建产物属 M2；当前 workflow 仍只跑 unittest（135 用例已在本地 Windows 全绿，Linux 未实测）。
4. **`insert_job` 的 PENDING/RUNNING 状态路径未在生产代码使用**（当前为完成时一次性写入），保留是为 API 预留与状态机完整性；谓词 `job_recorded` 与 `db_recorded` 等价。
5. **元数据 `parameters`/`validation` 为自由 dict**——schema_version 控制顶层结构，嵌套字段演化需在 `from_dict` 中按需补充校验。
6. `logs/` 与 `*.db` 已加入 .gitignore；根目录遗留的 `reset-summary.md`（未跟踪，内容与本项目无关）与 `dist/` 旧区未做处理。
