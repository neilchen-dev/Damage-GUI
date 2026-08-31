"""应用入口（瘦启动器）。

历史版本中此文件承载了数据读取、预处理、模型、评估、绘图与 GUI 全部逻辑；
现已按关注点拆分到各子包（见 README）。此处仅保留启动逻辑与向后兼容
re-export（旧脚本、旧测试与旧 joblib 模型文件的导入路径不变）。
"""
from __future__ import annotations

# ---- 向后兼容 re-export（勿删：旧 joblib 模型按 damage_gui.app.* 反序列化） ----
from damage_gui.config import APP_TITLE, CONFIG, Config  # noqa: F401
from damage_gui.data.loader import (  # noqa: F401
    Condition,
    DamageDataManager,
    DamageRecord,
    read_damage_matrix,
)
from damage_gui.data.preprocessing import (  # noqa: F401
    bilateral_filter,
    coordinate_axes,
    coordinate_grids,
    evaluation_fields,
    normalize_matrix_shape,
    roi_description,
    roi_mask_for_shape,
)
from damage_gui.evaluation.metrics import (  # noqa: F401
    extract_core_metrics,
    format_core_metrics,
    metric_row,
    safe_r2,
    spatial_metrics,
)

# ---- 启动入口 ----
# 注意：Tk GUI 的导入必须延迟到 main() 内——本模块同时承担旧 joblib
# 反序列化的兼容 re-export（见上），Web/无头运行时会 import damage_gui.app，
# 不能在模块导入期拉起 tkinter / damage_gui.gui.main_window。
from damage_gui.model.bundle import (  # noqa: F401
    DamageModelService,
    ModelBundle,
    TrainingCancelled,
    build_model,
)
from damage_gui.model.ood import OODDetector, OODReport  # noqa: F401
from damage_gui.model.pod import PODRBFDamageField  # noqa: F401
from damage_gui.model.rbf import RBFDamageField  # noqa: F401
from damage_gui.model.validation import make_splits  # noqa: F401
from damage_gui.optimization.aim import (  # noqa: F401
    AimOptimizationResult,
    optimize_aim,
)
from damage_gui.visualization.plots import (  # noqa: F401
    render_full_prediction,
    render_heatmaps,
)


def main() -> None:
    """桌面应用入口（Tk GUI 延迟导入）。"""
    from damage_gui.gui.main_window import main as run_desktop

    run_desktop()


if __name__ == "__main__":
    main()
