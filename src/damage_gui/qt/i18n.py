"""Qt-facing i18n re-export.

Rather than copy the whole dictionary we simply wrap the existing Tk
translator so the two front-ends share exactly the same catalog.
"""
from __future__ import annotations

from damage_gui.gui.i18n import (
    DEFAULT_LANGUAGE,
    SUPPORTED_LANGUAGES,
    TRANSLATIONS,
    Language,
    Translator,
)

__all__ = [
    "Translator",
    "TRANSLATIONS",
    "Language",
    "DEFAULT_LANGUAGE",
    "SUPPORTED_LANGUAGES",
]

# Presentation-only copy; shared Tk catalog remains unchanged.
QT_COPY = {
    "activity_type": ("类型", "Type"),
    "activity_status": ("状态", "Status"),
    "activity_detail": ("工况 / 明细", "Detail"),
    "activity_progress": ("进度", "Progress"),
    "activity_elapsed": ("耗时", "Elapsed"),
    "prediction_detail": ("预测详情", "Prediction Detail"),
    "restore_inputs": ("恢复输入", "Restore Inputs"),
    "history_write_failed": ("追溯记录写入失败", "History persistence failed"),
    "persistence_failed": ("预测完成；追溯记录写入失败", "Prediction completed; history persistence failed"),
    "metadata_unavailable": ("模型元数据不可用", "Metadata unavailable"),
    "model_file_unavailable": ("模型文件不可用", "Model file unavailable"),
    "model_level_mismatch": ("请先加载与恢复等级一致的模型。", "Load a model matching the restored level before predicting."),
    "shared_model_busy": ("另一预测任务正在运行，请稍后重试。", "Another prediction task is running; try again after it finishes."),
    "cancelled": ("预测已取消", "Prediction cancelled"),
    "input_section": ("输入", "Input"),
    "result_section": ("结果", "Result"),
    "maximum": ("最大强度", "Maximum"),
    "area": ("毁伤面积比例", "Damage area ratio"),
    "confidence": ("置信度", "Confidence"),
    "closing": ("预测完成后关闭窗口…", "Closing after prediction completes…"),
    "ready": ("就绪", "Ready"),
    "ready_title": ("模型已就绪", "Model ready"),
    "ready_body": ("在右侧设置输入工况并运行预测。", "Set input conditions in the inspector and run prediction."),
    "running": ("正在预测…", "Predicting…"),
    "running_title": ("正在运行预测…", "Running prediction…"),
    "failed": ("预测失败", "Prediction failed"),
    "failed_body": ("请检查输入后重试。详细信息见日志。", "Check inputs and try again. Details are available in Logs."),
    "predicted": ("预测毁伤场", "Predicted Damage Field"),
    "truth": ("真实毁伤场", "True Damage Field"),
    "error": ("误差（预测 − 真实）", "Error (Predicted − True)"),
    "intensity": ("毁伤强度", "Damage Intensity"),
    "error_scale": ("误差", "Error"),
    "prediction_success": ("预测  成功", "Prediction  SUCCESS"),
    "prediction_failed": ("预测  失败", "Prediction  FAILED"),
}

def qt_text(key, zh):
    return QT_COPY[key][0 if zh else 1]

TRACE_LABELS = {
    'confidence': ('置信度','Confidence'),
    'R2': ('R²','R²'), 'PeakIntensityError': ('峰值强度误差','Peak intensity error'),
    'CentroidError': ('质心误差 (m)','Centroid error (m)'),
    'PeakPositionError': ('峰值位置误差 (m)','Peak position error (m)'),
    'MeanRelativeError': ('平均相对误差','Mean relative error'),
    'P95HybridError': ('P95 混合误差','P95 hybrid error'),
    'id': ('任务 ID','Job ID'), 'kind': ('类型','Type'), 'status': ('状态','Status'),
    'created_at': ('创建时间','Created'), 'started_at': ('开始时间','Started'),
    'finished_at': ('完成时间','Completed'), 'model_id': ('模型 ID','Model ID'),
    'prediction_elapsed_ms': ('计算耗时 ms','Prediction elapsed ms'),
    'input_source': ('输入','Input'), 'duration_ms': ('任务耗时 ms','Job duration ms'),
    'error_summary': ('错误摘要','Error'), 'level': ('等级','Level'),
    'h': ('高度 m','Height m'), 'v': ('速度 m/s','Velocity m/s'), 'deg': ('角度 °','Angle °'),
    'peak_intensity': ('最大强度','Maximum'), 'damage_area_ratio': ('毁伤面积比例','Damage area ratio'),
    'ood_level': ('置信度','Confidence'), 'ood_distance': ('OOD 距离','OOD distance'),
    'app_version': ('软件版本','Software version'), 'training_data_hash': ('training_data_hash','training_data_hash'),
    'model_type': ('模型类型','Model type'), 'damage_level': ('模型等级','Model level'),
    'training_samples': ('训练样本','Training samples'), 'code_commit': ('代码版本','Code commit'),
    'artifact_path': ('模型文件','Model file'), 'output': ('输出','Output'),
}

def trace_label(key, zh):
    return TRACE_LABELS.get(key, (key,key))[0 if zh else 1]

VALIDATION_COPY = {
    'select_sample': ('选择样本行以查看真值、预测和误差。','Select a sample row to inspect truth, prediction and error.'),
    'title': ('验证','Validation'), 'ready': ('验证就绪：选择策略与真值目录，然后运行。','Validation ready: select a strategy and ground-truth directory.'),
    'unavailable': ('验证不可用：需要真值数据目录。','Validation unavailable: ground-truth data is required.'),
    'mode': ('验证模式','Validation mode'), 'layer': ('留出层','Held-out layer'), 'all_layers': ('全部层（折外评估）','All layers (out-of-fold)'),
    'seed': ('随机种子','Seed'), 'data': ('真值数据目录','Ground-truth directory'), 'metric_view': ('指标口径','Metric view'),
    'raw': ('Raw（原始场）','Raw'), 'smoothed': ('Smoothed（平滑场）','Smoothed'), 'run': ('运行验证','Run Validation'), 'cancel': ('取消','Cancel'),
    'hist_x': ('单样本 P95 混合误差 (%)','Per-sample P95 hybrid error (%)'),
    'hist_y': ('样本数','Samples'),
    'hist_p95': ('汇总 P95 混合误差','Aggregate P95 hybrid'),
    'distribution': ('样本 P95 混合误差分布','Sample P95 hybrid distribution'),
    'overview': ('验证概览','Overview'), 'samples': ('样本结果','Samples'), 'comparison': ('样本对比','Comparison'), 'complete': ('验证完成','Validation complete'),
    'cancelled': ('验证已取消','Validation cancelled'),
    'running': ('正在验证…','Running validation…'), 'failed': ('验证失败','Validation failed'), 'numerical': ('数值指标','Numerical'),
    'spatial': ('空间指标（固定 Raw 口径）','Spatial metrics (always Raw)'), 'reliability': ('可靠性 / OOD','Reliability / OOD'),
    'retrain': ('各折重新拟合所加载模型的方法与配置；不会替换当前模型。','Refits each fold using the loaded model method/configuration; the current model is unchanged.'),
    'missing_fields': ('历史样本场不可用；仅保留指标，不恢复矩阵。','Per-sample fields unavailable in history; metrics are retained without matrices.'),
    'export': ('导出摘要 JSON','Export Summary JSON'), 'restore': ('恢复验证设置','Restore Validation Settings'),
    'random': ('随机留出','Random Holdout'), 'leave_h_out': ('高度整层留出','Height-layer Holdout'),
    'leave_v_out': ('速度整层留出','Velocity-layer Holdout'), 'leave_deg_out': ('角度整层留出','Angle-layer Holdout'), 'corner': ('角落外推','Corner Extrapolation'),
    'random_help': ('按现有随机切分检查插值能力。','Uses the existing random split to assess interpolation.'),
    'layer_help': ('整层留出，评估未见工况层的泛化能力。','Holds out complete layers to assess unseen conditions.'),
    'corner_help': ('按速度和角度阈值留出区域；不包含高度边界。','Holds out the existing velocity/angle threshold region; no height boundary.'),
    'corner_v': ('角落速度下限','Corner minimum velocity'), 'corner_deg': ('角落角度下限','Corner minimum angle'),
    'test_size': ('随机测试集比例','Random test fraction'), 'worst': ('最差样本：按单项指标排序','Worst cases: sort by an individual metric'),
    'outside': ('全局支持域之外','Outside global support'), 'local': ('局部支持不足','Local support insufficient'),
}

def validation_text(key, zh):
    return VALIDATION_COPY[key][0 if zh else 1]

TRAINING_COPY = {
    'model_id': ('模型 ID', 'Model ID'),
    'training': ('训练', 'Training'), 'models': ('模型库', 'Model Registry'),
    'dataset': ('训练数据目录', 'Dataset directory'), 'browse': ('浏览…', 'Browse…'),
    'inspect': ('检查数据集', 'Inspect Dataset'), 'overview': ('数据集概览', 'Dataset Overview'),
    'summary': ('训练摘要', 'Training Summary'), 'spectrum': ('累计解释方差', 'Cumulative Explained Variance'),
    'level': ('毁伤等级', 'Level'), 'type': ('模型类型', 'Model Type'),
    'components': ('POD 分量', 'POD Components'), 'advanced': ('高级参数', 'Advanced Parameters'),
    'kernel': ('RBF 核函数', 'RBF Kernel'), 'epsilon': ('epsilon（0 = 默认）', 'epsilon (0 = default)'),
    'smoothing': ('RBF 平滑', 'RBF Smoothing'), 'seed': ('随机种子', 'Random Seed'),
    'test_size': ('内置留出比例', 'Built-in Holdout Fraction'),
    'align': ('质心对齐', 'Pattern Alignment'), 'run': ('运行训练', 'Run Training'),
    'cancel': ('取消', 'Cancel'), 'validate': ('验证模型', 'Validate Model'),
    'register': ('注册模型', 'Register Model'), 'activate': ('设为当前模型', 'Set Active'),
    'refresh': ('刷新', 'Refresh'), 'load': ('加载已有模型…', 'Load Existing Model…'),
    'related': ('相关任务', 'View Related Jobs'), 'validation_history': ('打开验证历史', 'Open Validation History'),
    'ready': ('选择目录并检查真实 DamageMatrix 数据。', 'Select a directory and inspect its DamageMatrix files.'),
    'unregistered': ('未注册模型', 'Unregistered Model'), 'registered': ('已注册模型', 'Registered Model'),
    'legacy': ('旧版模型 · 元数据不完整；仍可预测。', 'Legacy Model · Metadata incomplete; prediction available.'),
    'no_result': ('尚无训练结果', 'No training result'),
    'holdout_note': ('训练服务包含 Random 留出验证；以下为留出指标，不是 Training Fit。独立验证可在验证工作区运行。', 'The training service includes Random holdout validation. These are held-out metrics, not Training Fit. Use Validation for independent evaluation.'),
    'not_validated': ('尚无独立验证任务', 'No independent validation job'),
    'samples': ('样本', 'Samples'), 'valid': ('可读取', 'Readable'), 'errors': ('读取错误', 'Read errors'),
    'duplicates': ('重复工况', 'Duplicate conditions'), 'gaps': ('网格组合缺口（非缺失文件判定）', 'Grid combination gaps (not missing-file claims)'),
    'heights': ('高度层', 'Heights'), 'velocities': ('速度层', 'Velocities'), 'angles': ('角度层', 'Angles'),
    'source_shape': ('源场尺寸', 'Source Field Shape'), 'target_shape': ('建模尺寸', 'Modeling Shape'),
    'train_count': ('训练工况', 'Training Conditions'), 'test_count': ('留出工况', 'Held-out Conditions'),
    'loading_stage': ('读取训练矩阵', 'Loading Training Fields'), 'fitting_stage': ('拟合模型', 'Fitting Model'),
    'evaluating_stage': ('评估内置留出工况', 'Evaluating Built-in Holdout'),
    'duration': ('训练耗时', 'Training Duration'), 'software': ('软件版本', 'Software Version'),
    'current_app': ('应用当前模型', 'Current in Application'),
    'created': ('创建时间', 'Created'), 'status': ('状态', 'Status'), 'hash': ('训练数据指纹', 'Training Data Hash'),
    'config': ('训练配置', 'Training Configuration'), 'commit': ('代码提交', 'Code Commit'),
    'path': ('模型文件', 'Model File'), 'exists': ('文件存在', 'File Exists'), 'size': ('文件大小 bytes', 'File Size bytes'),
    'training_job': ('训练任务', 'Training Job'), 'output': ('输出模型 ID', 'Output Model ID'),
    'all': ('全部', 'All'), 'search': ('搜索模型 ID', 'Search Model ID'),
    'UNREGISTERED': ('未注册', 'Unregistered'),
    'ACTIVE': ('已激活', 'Active'), 'AVAILABLE': ('可用', 'Available'),
    'LEGACY': ('旧版', 'Legacy'), 'MISSING': ('文件缺失', 'Missing File'), 'ARCHIVED': ('已归档', 'Archived'),
    'no_spectrum': ('该模型无 POD 方差数据', 'No POD variance data for this model'),
    'busy': ('科学任务运行中，模型绑定已锁定。', 'Scientific job running; model binding locked.'),
    'trace_failed': ('追溯保存失败，详情见日志。', 'Traceability persistence failed; see Logs.'),
    'inspection_failed': ('数据检查失败', 'Dataset Inspection Failed'),
    'invalid': ('所选等级包含无效数据或重复工况，不能提交训练。', 'Selected level has invalid data or duplicate conditions; training disabled.'),
    'available_note': ('激活遵循现有生命周期。归档为终态；已有验证证据不表示质量通过。', 'Activation follows the existing lifecycle. Archived is terminal; recorded validation evidence is not a quality verdict.'),
    'load_time': ('数据检查耗时', 'Dataset Inspection Time'),
}

def training_text(key, zh):
    return TRAINING_COPY.get(key, (key, key))[0 if zh else 1]


def training_stage(stage, zh):
    for marker,key in [('读取','loading_stage'),('拟合','fitting_stage'),('评估','evaluating_stage')]:
        if marker in stage:
            return training_text(key,zh)
    return stage
