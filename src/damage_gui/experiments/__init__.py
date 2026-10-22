"""实验框架（M3.1 消融研究 + M3.2 基线对比）。

本包属于**研究脚本层**。2026-10 起全包改用 :mod:`damage_gui.data.table`
（Table/read_csv），不再依赖 pandas——整个 ``src/`` 树自此零 pandas、
零 sklearn。PEP 562 惰性解析保留：访问 ``damage_gui.experiments.X`` 时
才按需导入子模块，避免 import 期拉起 scipy/numpy 全链。

基线模型（LinearInterpField / NearestNeighborField）已于 2026-10 下沉至
:mod:`damage_gui.model.baselines` —— 核心训练链路（model.bundle）直接
使用它们，不属于研究层；此处保留包级导出以兼容既有研究脚本。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover —— 仅供类型检查与 IDE 补全
    from damage_gui.experiments.runner import (
        ExperimentResult,
        ExperimentSpec,
        baseline_specs,
        design_quadrant_specs,
        pod_sweep_specs,
        rbf_param_specs,
        run_experiment,
        run_suite,
        save_report,
        validation_specs,
    )
    from damage_gui.model.baselines import (
        LinearInterpField,
        NearestNeighborField,
    )

_EXPORTS: dict[str, tuple[str, str]] = {
    # 轻量、无 pandas —— 已下沉至 model 层（核心训练链路直接使用）
    "LinearInterpField": ("damage_gui.model.baselines", "LinearInterpField"),
    "NearestNeighborField": ("damage_gui.model.baselines", "NearestNeighborField"),
    # 以下为研究层符号（runner 依赖 model.bundle 全链），按需解析
    "ExperimentResult": ("damage_gui.experiments.runner", "ExperimentResult"),
    "ExperimentSpec": ("damage_gui.experiments.runner", "ExperimentSpec"),
    "baseline_specs": ("damage_gui.experiments.runner", "baseline_specs"),
    "design_quadrant_specs": ("damage_gui.experiments.runner", "design_quadrant_specs"),
    "pod_sweep_specs": ("damage_gui.experiments.runner", "pod_sweep_specs"),
    "rbf_param_specs": ("damage_gui.experiments.runner", "rbf_param_specs"),
    "run_experiment": ("damage_gui.experiments.runner", "run_experiment"),
    "run_suite": ("damage_gui.experiments.runner", "run_suite"),
    "save_report": ("damage_gui.experiments.runner", "save_report"),
    "validation_specs": ("damage_gui.experiments.runner", "validation_specs"),
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    try:
        module_name, attr = _EXPORTS[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None

    from importlib import import_module

    value = getattr(import_module(module_name), attr)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_EXPORTS))
