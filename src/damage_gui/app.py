"""应用入口（瘦启动器 + 惰性兼容层）。

历史版本中此文件承载了数据读取、预处理、模型、评估、绘图与 GUI 全部逻辑；
现已按关注点拆分到各子包（见 README）。此处保留启动逻辑与向后兼容
re-export（旧脚本、旧测试与旧 joblib 模型文件的导入路径不变）。

兼容性 re-export 采用 PEP 562 模块级 ``__getattr__`` **惰性解析**：
``import damage_gui.app`` 不再于导入期拉起 numpy/scipy/sklearn/pandas/
matplotlib 全栈（实测 0.93s → 0.04s），只有真正访问 ``damage_gui.app.X``
时才按需导入对应子模块。旧 joblib 反序列化走的是属性访问路径，不受影响。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover —— 仅供类型检查器与 IDE 补全
    from damage_gui.config import APP_TITLE, CONFIG, Config
    from damage_gui.data.loader import (
        Condition,
        DamageDataManager,
        DamageRecord,
        read_damage_matrix,
    )
    from damage_gui.data.preprocessing import (
        bilateral_filter,
        coordinate_axes,
        coordinate_grids,
        evaluation_fields,
        normalize_matrix_shape,
        roi_description,
        roi_mask_for_shape,
    )
    from damage_gui.evaluation.metrics import (
        extract_core_metrics,
        format_core_metrics,
        metric_row,
        safe_r2,
        spatial_metrics,
    )
    from damage_gui.model.bundle import (
        DamageModelService,
        ModelBundle,
        TrainingCancelled,
        build_model,
    )
    from damage_gui.model.ood import OODDetector, OODReport
    from damage_gui.model.pod import PODRBFDamageField
    from damage_gui.model.rbf import RBFDamageField
    from damage_gui.model.validation import make_splits
    from damage_gui.optimization.aim import AimOptimizationResult, optimize_aim
    from damage_gui.visualization.plots import render_full_prediction, render_heatmaps

# ---- 向后兼容 re-export 表（勿删：旧 joblib 模型按 damage_gui.app.* 反序列化） ----
# 名称 -> (子模块, 属性名)；属性访问时按需导入，避免 import 期全栈加载。
_COMPAT_EXPORTS: dict[str, tuple[str, str]] = {
    "APP_TITLE": ("damage_gui.config", "APP_TITLE"),
    "CONFIG": ("damage_gui.config", "CONFIG"),
    "Config": ("damage_gui.config", "Config"),
    "Condition": ("damage_gui.data.loader", "Condition"),
    "DamageDataManager": ("damage_gui.data.loader", "DamageDataManager"),
    "DamageRecord": ("damage_gui.data.loader", "DamageRecord"),
    "read_damage_matrix": ("damage_gui.data.loader", "read_damage_matrix"),
    "bilateral_filter": ("damage_gui.data.preprocessing", "bilateral_filter"),
    "coordinate_axes": ("damage_gui.data.preprocessing", "coordinate_axes"),
    "coordinate_grids": ("damage_gui.data.preprocessing", "coordinate_grids"),
    "evaluation_fields": ("damage_gui.data.preprocessing", "evaluation_fields"),
    "normalize_matrix_shape": (
        "damage_gui.data.preprocessing",
        "normalize_matrix_shape",
    ),
    "roi_description": ("damage_gui.data.preprocessing", "roi_description"),
    "roi_mask_for_shape": ("damage_gui.data.preprocessing", "roi_mask_for_shape"),
    "extract_core_metrics": ("damage_gui.evaluation.metrics", "extract_core_metrics"),
    "format_core_metrics": ("damage_gui.evaluation.metrics", "format_core_metrics"),
    "metric_row": ("damage_gui.evaluation.metrics", "metric_row"),
    "safe_r2": ("damage_gui.evaluation.metrics", "safe_r2"),
    "spatial_metrics": ("damage_gui.evaluation.metrics", "spatial_metrics"),
    "DamageModelService": ("damage_gui.model.bundle", "DamageModelService"),
    "ModelBundle": ("damage_gui.model.bundle", "ModelBundle"),
    "TrainingCancelled": ("damage_gui.model.bundle", "TrainingCancelled"),
    "build_model": ("damage_gui.model.bundle", "build_model"),
    "OODDetector": ("damage_gui.model.ood", "OODDetector"),
    "OODReport": ("damage_gui.model.ood", "OODReport"),
    "PODRBFDamageField": ("damage_gui.model.pod", "PODRBFDamageField"),
    "RBFDamageField": ("damage_gui.model.rbf", "RBFDamageField"),
    "make_splits": ("damage_gui.model.validation", "make_splits"),
    "AimOptimizationResult": ("damage_gui.optimization.aim", "AimOptimizationResult"),
    "optimize_aim": ("damage_gui.optimization.aim", "optimize_aim"),
    "render_full_prediction": ("damage_gui.visualization.plots", "render_full_prediction"),
    "render_heatmaps": ("damage_gui.visualization.plots", "render_heatmaps"),
}

__all__ = sorted(_COMPAT_EXPORTS)


def __getattr__(name: str) -> Any:
    """按需解析旧版全量 re-export（PEP 562）。"""
    try:
        module_name, attr = _COMPAT_EXPORTS[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None

    from importlib import import_module

    value = getattr(import_module(module_name), attr)
    # 解析一次后写入模块字典，后续访问退化为普通属性查找
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_COMPAT_EXPORTS))


def main() -> None:
    """桌面应用入口（GUI 延迟导入）。"""
    from damage_gui.desktop import main as run_desktop

    run_desktop()


if __name__ == "__main__":
    main()
