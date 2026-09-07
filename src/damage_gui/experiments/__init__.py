"""实验框架（M3.1 消融研究 + M3.2 基线对比）。"""
from damage_gui.experiments.baselines import LinearInterpField, NearestNeighborField
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

__all__ = [
    "ExperimentResult",
    "ExperimentSpec",
    "LinearInterpField",
    "NearestNeighborField",
    "baseline_specs",
    "design_quadrant_specs",
    "pod_sweep_specs",
    "rbf_param_specs",
    "run_experiment",
    "run_suite",
    "save_report",
    "validation_specs",
]
