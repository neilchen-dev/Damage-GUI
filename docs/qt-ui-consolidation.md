# Phase 2.4 — UI Consolidation & Desktop UX Polish

本轮仅整理 Qt 桌面 UI。此前未接入的 reliability/session 草稿已移除；没有新增 Recovery、Backup、Audit、Aim，没有改算法、SQLite schema 或 TaskManager。此前阶段的未提交改动保留。

1. **UI consolidation**：六个核心页面统一 WorkspaceHeader、标题/上下文层级、分区详情、表格、状态颜色及元数据显示。保留 Application Bar / Tool Rail / Workspace / 280 px Inspector / Activity Panel 和已定稿的科学配色。明暗壳层没有重新设计。
2. **公共组件**：新增 `widgets/workspace.py` 的 WorkspaceHeader、DetailView、CopyableValue、EmptyState、scroll_inspector，以及 `widgets/workflow_table.py` 的 WorkflowTable。StatusIndicator 和状态角色映射复用现有 StatusBadge/theme。详情使用共享分区和键值行，原始 metadata 仅在默认关闭的 Advanced Metadata 中。保留 plain-text accessor 给已有结果展示和测试，完整值不作为主显示文本。没有引入新的业务框架。
3. **Training Summary**：MODEL / DATASET / EXECUTION / BUILT-IN HOLDOUT，展示真实模型名与 K、等级、模型 ID、训练/留出数、hash、耗时、软件、commit，以及 Raw/Smoothed 留出指标。MRE/P95 为百分比，R²/RMSE/MAE 使用简洁数值；没有把既有留出报告称为 Training Fit。Dataset Overview 也改为分区统计，源数据结构放在折叠 metadata 中。
4. **Registry Detail**：MODEL / PROVENANCE / TRAINING / VALIDATION / ARTIFACT。元数据、训练任务、最近验证和文件事实独立展示；长 ID/hash/path 缩略，tooltip 和 Copy 保留完整值。Legacy/Missing 和原注册/激活规则不变。新增统一空态，Train Model 直接导航现有训练页，Load Existing 保留。
5. **Validation Overview**：NUMERICAL / SPATIAL / RELIABILITY-OOD / EXECUTION。保留 Raw/Smoothed 的原有展示选择，空间口径仍固定 Raw，不新增评分或指标算法。HIGH/MEDIUM/LOW 分开计数，数值目标与可靠性不混为质量结论。参数和原始报告放入折叠 metadata。
6. **History Detail**：统一 JOB / INPUT / RESULT / MODEL / TRACEABILITY，原始 job/model 在 Advanced Metadata 中。Prediction、Batch、Validation、Training 填入已有数据，缺失 metadata/artifact 继续显示原有 fallback。Restore Inputs / Restore Validation Settings 保持原行为，不自动运行。历史查询、分页和 SQLite 结构没有改动；分页文案不再显示开发式 `page ≤ 1000`。
7. **小功能**：表格右键 Copy Cell / Copy Row，Ctrl/Cmd+C 复制选中行；ID/hash/path 的右键复制取完整值。Batch preview 和 Validation samples 增加当前已加载表格搜索，Validation 的 P95/MRE/Dice 按钮仅触发普通排序。Registry/History 搜索继续使用已有输入。View 增加 Inspector toggle、Activity toggle 和 Reset Layout。模型菜单集中 Load / Current Model Details / Registry；文件菜单提供现有 Dataset Browse、Batch CSV Browse 和 Export Current View。没有加 MRU 存储、工作区持久化或设置系统。
8. **快捷键**：Ctrl/Cmd+O 保留 Load Model；Ctrl/Cmd+R 只在当前页有可用 Run 时启用；Ctrl/Cmd+F 聚焦当前搜索框（Registry、History、Batch preview、Validation samples）；Ctrl/Cmd+E 只调用 Prediction PNG 或 Validation JSON 的现有导出；Ctrl/Cmd+L 展开 Logs，再按收起。Registry / History 不绑定 Run。现有 F5 预测快捷键保留。导出成功通过 Activity 显示 Exported + basename，不新增 modal。
9. **1280×720 / 1100×700**：六页中英文均已截图。主运行/注册动作和 280 px Inspector 保持可用；较长详情垂直滚动，表格保留列调整和必要的横向滚动。不会要求所有低优先级 metadata 同时显示。共享详情禁止横向撑宽；旧控件在语言切换时先隐藏，避免旧/新文案叠画。
10. **1440×900**：六页均提供最终截图，适合作为 README 展示素材：`outputs/qt_phase24_ui/prediction_en_1440x900.png`、`batch_en_1440x900.png`、`validation_en_1440x900.png`、`training_en_1440x900.png`、`models_en_1440x900.png`、`history_en_1440x900.png`。
11. **中英文截图与视觉审计**：`outputs/qt_phase24_ui/` 共 40 张。六页 × 两种语言 × 三种尺寸共 36 张，另有 Registry empty、Validation sort/comparison、Export success。逐页检查 Header、Inspector、Sections、Table、Buttons、Status、Spacing、Typography、Empty/Error fallback；修复了旧详情残影、长 ID 撑宽检查器、深色背景按钮对比不足、复制与显示混用完整值等问题。科学视图继续使用现有 damage_dark_cividis / error_dark_coolwarm；仅统一标题/工具栏和布局。截图是人工验收材料，不建立像素比较基线。
12. **测试**：全量 259 passed / 1 skipped；原 Prediction、Batch、Validation、Training、Registry、History、CLI、Web、Tk 和数值测试保留。新增结构与真实工作流验收，覆盖公共 header/section/status、完整值复制、表格选中复制、搜索、当前页命令、Inspector/Activity toggle、双语、三种尺寸，以及 Dataset → Training → Register → Activate → Validation → Prediction → Batch → History。`git diff --check` 通过。
13. **已知 UI 限制**：较长详情和完整指标需垂直滚动；窄窗口表格需横向滚动查看次要列。Advanced Metadata 保留真实程序字段名与原始 JSON。模型文件旧 Load/Save 入口仍保留既有同步行为；本轮没有扩展为文件处理平台。近期模型/文件 MRU、历史全筛选导出、主题/导出目录偏好均未增加。只完成 macOS offscreen 验收，Windows/Linux 原生窗口、系统文件对话框和辅助功能仍需发布前人工确认。旧通用 Save Model 的部分错误弹窗行为没有全面替换。
14. **是否结束 Qt 重构**：建议结束大范围 Qt 重构，以本轮界面为稳定基线。接下来只做具体可复现的 UI 修复、原生系统发布验收和文案小修；不继续为“系统完整性”增加底层平台能力。

截图 checklist：

| 页面 | Header / Inspector | 详情 / 表格 | 按钮 / 状态 | 三种尺寸 / 双语 |
|---|---|---|---|---|
| Prediction | 公共页头、可滚动检查器 | 原科学视图与已有模型字段 | 原主运行、公共状态、导出提示 | 已检查 |
| Batch | 公共页头、可滚动检查器 | 公共表格、预览搜索 | 主运行、现有结果 Open/Folder/Copy | 已检查 |
| Validation | 公共页头、可滚动检查器 | 分组指标、公共样本表、排序 | 主运行、取消、JSON、公共状态 | 已检查 |
| Training | 公共页头、原可滚动检查器 | 分组摘要、真实 POD 图 | 主运行、Validate、Register | 已检查 |
| Registry | 公共页头、可滚动检查器 | 五区详情、公共表格、统一空态 | 原 Activate/Register/History | 已检查 |
| History | 公共页头、可滚动检查器 | 五区详情、公共表格 | 原筛选/分页/Restore、公共状态 | 已检查 |

本轮主要代码位于 `src/damage_gui/qt/`，新增验收入口 `scripts/capture_qt_consolidation.py` 和 `tests/test_qt_consolidation.py`。输出 ID 与数据库路径见 `outputs/qt_phase24_ui/evidence.json`。

复现：

```sh
QT_QPA_PLATFORM=offscreen .venv/bin/python scripts/capture_qt_consolidation.py
.venv/bin/python -m pytest -q
```
