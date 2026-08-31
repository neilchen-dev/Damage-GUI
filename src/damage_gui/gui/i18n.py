"""Small, dependency-free localization layer for the desktop workbench.

The scientific model and persisted configuration remain language-neutral.  This
module only owns user-facing desktop copy so the same window can switch between
Simplified Chinese and English without rebuilding the process.
"""

from __future__ import annotations

from collections.abc import Callable

Language = str
SUPPORTED_LANGUAGES = ("zh", "en")
DEFAULT_LANGUAGE = "zh"

TRANSLATIONS: dict[str, dict[str, str]] = {
    "app.title": {
        "zh": "基于数据驱动的毁伤效能快速评估方法研究",
        "en": "DamageLab — Damage-Field Prediction & Analysis",
    },
    "language.label": {"zh": "语言", "en": "Language"},
    "language.zh": {"zh": "中文", "en": "Chinese"},
    "language.en": {"zh": "English", "en": "English"},
    "menu.file": {"zh": "文件", "en": "File"},
    "menu.view": {"zh": "视图", "en": "View"},
    "menu.model": {"zh": "模型", "en": "Model"},
    "menu.analysis": {"zh": "分析", "en": "Analysis"},
    "menu.results": {"zh": "结果", "en": "Results"},
    "menu.help": {"zh": "帮助", "en": "Help"},
    "menu.open_model": {"zh": "加载模型…", "en": "Open Model…"},
    "menu.save_model": {"zh": "保存模型…", "en": "Save Model…"},
    "menu.export_csv": {"zh": "导出 CSV…", "en": "Export CSV…"},
    "menu.export_png": {"zh": "导出 PNG…", "en": "Export PNG…"},
    "menu.exit": {"zh": "退出", "en": "Exit"},
    "menu.reset_panes": {"zh": "重置面板尺寸", "en": "Reset Pane Sizes"},
    "menu.train": {"zh": "训练模型", "en": "Train Model"},
    "menu.cancel_training": {"zh": "取消训练", "en": "Cancel Training"},
    "menu.run_prediction": {"zh": "运行预测", "en": "Run Prediction"},
    "menu.batch_prediction": {"zh": "批量预测", "en": "Batch Prediction"},
    "menu.aim": {"zh": "瞄准优化", "en": "Aim Optimization"},
    "menu.stop": {"zh": "停止当前任务", "en": "Stop Current Task"},
    "menu.dataset": {"zh": "数据集", "en": "Dataset"},
    "menu.prediction": {"zh": "预测", "en": "Prediction"},
    "menu.history": {"zh": "历史记录", "en": "History"},
    "menu.export": {"zh": "导出", "en": "Export"},
    "menu.help_about": {"zh": "关于 DamageLab", "en": "About DamageLab"},
    "toolbar.open": {"zh": "打开", "en": "Open"},
    "toolbar.save": {"zh": "保存", "en": "Save"},
    "toolbar.run": {"zh": "运行", "en": "Run"},
    "toolbar.stop": {"zh": "停止", "en": "Stop"},
    "navigation.title": {"zh": "导航", "en": "Navigation"},
    "navigation.project": {"zh": "项目", "en": "Project"},
    "navigation.analysis": {"zh": "分析", "en": "Analysis"},
    "navigation.results": {"zh": "结果", "en": "Results"},
    "nav.dataset": {"zh": "数据集", "en": "Dataset"},
    "nav.model": {"zh": "模型", "en": "Model"},
    "nav.validation": {"zh": "验证", "en": "Validation"},
    "nav.prediction": {"zh": "预测", "en": "Prediction"},
    "nav.batch": {"zh": "批量预测", "en": "Batch Prediction"},
    "nav.aim": {"zh": "瞄准优化", "en": "Aim Optimization"},
    "nav.history": {"zh": "历史记录", "en": "History"},
    "nav.export": {"zh": "导出", "en": "Export"},
    "properties.title": {"zh": "属性", "en": "Properties"},
    "visualization.title": {"zh": "毁伤场", "en": "Damage Field"},
    "visualization.no_prediction": {"zh": "暂无预测结果。", "en": "No prediction yet."},
    "visualization.view": {"zh": "视图", "en": "View"},
    "visualization.fit": {"zh": "适配窗口", "en": "Fit"},
    "visualization.triple": {"zh": "对比三联图", "en": "Comparison"},
    "visualization.full": {"zh": "全视图预测图", "en": "Full Prediction"},
    "visualization.aim": {"zh": "瞄准优化图", "en": "Aim Optimization"},
    "visualization.single_title": {
        "zh": "毁伤场 — 单工况预测",
        "en": "Damage Field — Single Prediction",
    },
    "visualization.aim_title": {
        "zh": "毁伤场 — 瞄准优化",
        "en": "Damage Field — Aim Optimization",
    },
    "visualization.aim_empty": {
        "zh": "请先运行预测，再执行优化",
        "en": "Run a prediction before optimizing",
    },
    "results.title": {"zh": "结果", "en": "Results"},
    "results.result": {"zh": "预测结果", "en": "Result"},
    "results.validation": {"zh": "验证指标", "en": "Validation"},
    "results.reliability": {"zh": "可信度", "en": "Reliability"},
    "results.run": {"zh": "运行信息", "en": "Run Info"},
    "results.advisory": {"zh": "建议", "en": "Advisory"},
    "results.maximum": {"zh": "最大值", "en": "Maximum"},
    "results.area": {"zh": "毁伤面积", "en": "Damaged Area"},
    "results.grid": {"zh": "网格", "en": "Grid"},
    "results.mean_error": {"zh": "平均相对误差", "en": "Mean Rel. Error"},
    "results.p95_error": {"zh": "P95 混合误差", "en": "P95 Hybrid Error"},
    "results.confidence": {"zh": "可信度", "en": "Confidence"},
    "results.ood_distance": {"zh": "OOD 距离", "en": "OOD Distance"},
    "results.inside_hull": {"zh": "位于训练凸包内", "en": "Inside Hull"},
    "results.local_support": {"zh": "局部支撑", "en": "Local Support"},
    "results.elapsed": {"zh": "耗时", "en": "Elapsed"},
    "results.model": {"zh": "模型", "en": "Model"},
    "results.empty_advice": {
        "zh": "训练或预测完成后显示建议。",
        "en": "Run training or prediction to see guidance.",
    },
    "status.ready": {"zh": "就绪", "en": "Ready"},
    "status.running": {"zh": "运行中", "en": "Running"},
    "status.complete": {"zh": "完成", "en": "Complete"},
    "status.error": {"zh": "错误", "en": "Error"},
    "status.initial": {
        "zh": "请选择数据目录并训练模型。",
        "en": "Select a dataset directory and train a model.",
    },
    "status.no_model": {"zh": "尚未加载模型。", "en": "No model loaded."},
    "status.no_model_yet": {"zh": "尚未加载模型。", "en": "No model loaded yet."},
    "status.no_prediction": {"zh": "暂无预测结果。", "en": "No prediction yet."},
    "status.no_validation": {
        "zh": "暂无验证指标。",
        "en": "No validation metrics available.",
    },
    "status.no_ood": {"zh": "暂无 OOD 报告。", "en": "No OOD report available."},
    "status.no_optimization": {"zh": "暂无优化结果。", "en": "No optimization yet."},
    "panel.dataset": {"zh": "数据集配置", "en": "Dataset Configuration"},
    "panel.directory": {"zh": "目录", "en": "Directory"},
    "panel.damage_level": {"zh": "毁伤等级", "en": "Damage Level"},
    "panel.dataset_summary": {"zh": "数据集摘要", "en": "Dataset Summary"},
    "panel.no_dataset": {"zh": "尚未扫描数据集。", "en": "No dataset scanned yet."},
    "panel.files_discovered": {"zh": "发现文件数", "en": "Files discovered"},
    "panel.level_samples": {"zh": "等级 {level} 样本数", "en": "Level {level} samples"},
    "panel.unavailable": {
        "zh": "不可用\n请检查所选目录。",
        "en": "Unavailable\nCheck the selected directory.",
    },
    "panel.browse": {"zh": "浏览…", "en": "Browse…"},
    "panel.model": {"zh": "模型配置", "en": "Model Configuration"},
    "panel.model_type": {"zh": "模型类型", "en": "Model Type"},
    "panel.pod_components": {"zh": "POD 分量 K", "en": "POD Components K"},
    "panel.validation_mode": {"zh": "验证方式", "en": "Validation Mode"},
    "panel.model_status": {"zh": "模型状态", "en": "Model Status"},
    "panel.train": {"zh": "训练模型", "en": "Train Model"},
    "panel.cancel": {"zh": "取消", "en": "Cancel"},
    "panel.load": {"zh": "加载", "en": "Load"},
    "panel.save": {"zh": "保存", "en": "Save"},
    "panel.no_model_yet": {"zh": "尚未加载模型。", "en": "No model loaded yet."},
    "panel.validation": {"zh": "验证配置", "en": "Validation Configuration"},
    "panel.active_mode": {"zh": "当前方式", "en": "Active Mode"},
    "panel.validation_result": {"zh": "验证结果", "en": "Validation Result"},
    "panel.no_validation_result": {
        "zh": "暂无验证结果。",
        "en": "No validation results yet.",
    },
    "panel.prediction": {"zh": "单工况预测", "en": "Single Prediction"},
    "panel.height": {"zh": "高度 h", "en": "Height h"},
    "panel.velocity": {"zh": "速度 v", "en": "Velocity v"},
    "panel.angle": {"zh": "角度 θ", "en": "Angle θ"},
    "panel.run_prediction": {"zh": "运行预测", "en": "Run Prediction"},
    "panel.reliability": {"zh": "可信度", "en": "Reliability"},
    "panel.batch": {"zh": "批量输入", "en": "Batch Input"},
    "panel.input_csv": {
        "zh": "输入 CSV（job_id,h,v,deg,level）",
        "en": "Input CSV (job_id,h,v,deg,level)",
    },
    "panel.no_batch_file": {
        "zh": "尚未选择批量文件。",
        "en": "No batch file selected yet.",
    },
    "panel.run_batch": {"zh": "运行批量预测", "en": "Run Batch"},
    "panel.aim": {"zh": "瞄准优化", "en": "Aim Optimization"},
    "panel.spread_mode": {"zh": "散布模式", "en": "Spread Mode"},
    "panel.optimize": {"zh": "执行优化", "en": "Optimize"},
    "panel.cep": {"zh": "CEP", "en": "CEP"},
    "panel.rep": {"zh": "REP", "en": "REP"},
    "panel.dep": {"zh": "DEP", "en": "DEP"},
    "panel.correlation": {"zh": "相关系数 ρ", "en": "Correlation ρ"},
    "panel.rotation": {"zh": "旋转角 θ", "en": "Rotation θ"},
    "panel.export": {"zh": "导出当前结果", "en": "Export Current Result"},
    "panel.export_note": {
        "zh": "导出当前预测矩阵或选中的科学图形。",
        "en": "Export the current prediction matrix or selected scientific figure.",
    },
    "panel.export_csv": {"zh": "导出 CSV…", "en": "Export CSV…"},
    "panel.export_png": {"zh": "导出 PNG…", "en": "Export PNG…"},
    "panel.history": {"zh": "历史记录", "en": "History"},
    "panel.history_note": {
        "zh": "运行记录保存在现有 SQLite 追溯数据库中。\n此桌面视图为紧凑只读视图。",
        "en": "Runs are recorded in the existing SQLite traceability database.\n"
        "This desktop view is compact and read-only.",
    },
    "panel.database": {"zh": "数据库", "en": "Database"},
    "choice.rbf": {"zh": "RBF 插值场", "en": "RBF Interpolated Field"},
    "choice.pod_rbf": {"zh": "POD-RBF 降阶模型", "en": "POD-RBF Reduced Model"},
    "choice.validation.random": {
        "zh": "随机留出 Random Holdout",
        "en": "Random Holdout",
    },
    "choice.validation.leave_h_out": {
        "zh": "按高度整层留出 Leave-h-out",
        "en": "Leave-h-out",
    },
    "choice.validation.leave_v_out": {
        "zh": "按速度整层留出 Leave-v-out",
        "en": "Leave-v-out",
    },
    "choice.validation.leave_deg_out": {
        "zh": "按角度整层留出 Leave-deg-out",
        "en": "Leave-deg-out",
    },
    "choice.validation.corner": {
        "zh": "角落外推 Corner Holdout",
        "en": "Corner Holdout",
    },
    "common.yes": {"zh": "是", "en": "Yes"},
    "common.no": {"zh": "否", "en": "No"},
    "common.unknown": {"zh": "未知", "en": "Unknown"},
    "common.target": {"zh": "目标", "en": "Target"},
    "common.outside_hull": {"zh": "位于训练凸包外", "en": "Outside the training hull"},
    "common.sparse_support": {
        "zh": "局部训练支撑稀疏",
        "en": "Local training support is sparse",
    },
    "ood.high": {"zh": "高（插值区域）", "en": "High (interpolation region)"},
    "ood.medium": {"zh": "中（稀疏支撑区域）", "en": "Medium (sparse support)"},
    "ood.low": {"zh": "低（外推区域）", "en": "Low (extrapolation region)"},
    "reliability.summary": {
        "zh": "{level} · 距离 {distance:.3f}",
        "en": "{level} · distance {distance:.3f}",
    },
    "reliability.outside": {
        "zh": "位于训练凸包外",
        "en": "Outside the training hull",
    },
    "reliability.sparse": {
        "zh": "局部训练支撑稀疏",
        "en": "Local training support is sparse",
    },
    "common.coverage_edge": {"zh": "训练数据覆盖边缘", "en": "edge of training coverage"},
    "model.level_samples": {
        "zh": "等级 {level} · {train} 个训练样本 / {test} 个测试样本",
        "en": "Level {level} · {train} train / {test} test samples",
    },
    "model.validation": {"zh": "验证：{label}", "en": "Validation: {label}"},
    "model.id": {"zh": "ID：{id}", "en": "ID: {id}"},
    "model.legacy": {
        "zh": "旧版模型（无元数据）",
        "en": "Legacy model without metadata",
    },
    "model.training": {"zh": "训练耗时：{seconds:.1f} 秒", "en": "Training: {seconds:.1f} s"},
    "metrics.mean": {"zh": "平均相对误差：{value:.2%}", "en": "Mean relative error: {value:.2%}"},
    "metrics.p95": {"zh": "P95 混合误差：{value:.2%}", "en": "P95 hybrid error: {value:.2%}"},
    "metrics.target": {"zh": "目标：< {value:.0%}", "en": "Target: < {value:.0%}"},
    "advice.no_metrics": {
        "zh": "训练或预测完成后显示结论。",
        "en": "Guidance appears after training or prediction.",
    },
    "advice.pass": {
        "zh": "{scope}核心指标全部达标（目标 <{target:.0%}）。可导出结果存档。",
        "en": "All {scope} core metrics meet the target (<{target:.0%}). Results can be archived.",
    },
    "advice.p95": {
        "zh": "{scope}平均精度达标，但 P95 混合误差超标。建议定位误差并加密附近工况。",
        "en": "{scope} mean accuracy meets the target, but P95 hybrid error does not. "
        "Inspect the error and densify nearby conditions.",
    },
    "advice.fail": {
        "zh": "{scope}核心指标未达标。建议确认数据完整并加密训练工况网格。",
        "en": "{scope} core metrics do not meet the target. Check data completeness "
        "and densify the training grid.",
    },
    "validation.summary": {
        "zh": "平均相对误差：{mean:.2%}\nP95 混合误差：{p95:.2%}\n目标：< {target:.0%}",
        "en": "Mean relative error: {mean:.2%}\nP95 hybrid error: {p95:.2%}\n"
        "Target: < {target:.0%}",
    },
}


class Translator:
    """Observable translation catalog shared by all desktop components."""

    def __init__(self, language: Language = DEFAULT_LANGUAGE) -> None:
        self.language = language if language in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
        self._listeners: list[Callable[[], None]] = []

    def t(self, key: str, **values: object) -> str:
        catalog = TRANSLATIONS.get(key)
        if catalog is None:
            text = key
        else:
            text = catalog.get(self.language) or catalog.get(DEFAULT_LANGUAGE) or key
        return text.format(**values) if values else text

    def subscribe(self, listener: Callable[[], None]) -> None:
        if listener not in self._listeners:
            self._listeners.append(listener)

    def set_language(self, language: Language) -> bool:
        if language not in SUPPORTED_LANGUAGES or language == self.language:
            return False
        self.language = language
        for listener in tuple(self._listeners):
            listener()
        return True

    def language_label(self, language: Language | None = None) -> str:
        selected = language or self.language
        return self.t("language.zh" if selected == "zh" else "language.en")

    def language_choices(self) -> tuple[str, str]:
        return tuple(self.language_label(language) for language in SUPPORTED_LANGUAGES)

    def language_from_label(self, label: str) -> Language | None:
        for language in SUPPORTED_LANGUAGES:
            if self.language_label(language) == label:
                return language
        return None
